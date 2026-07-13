"""Attendance correction: device-authoritative, non-destructive effective-layer updates."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_correction import AttendanceCorrection
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.employee import Employee
from app.services.attendance_effective_service import (
    DayAttendanceSnapshot,
    apply_correction_to_effective_punches,
    load_day_snapshot_effective,
    rebuild_sessions_for_employee_date,
    verify_imported_timestamps,
)
from app.services.attendance_lock_service import employee_day_lock
from app.services.attendance_service import (
    _insert_sync_suppressions_idempotent,
    reimport_attendance_window,
)
from app.services.audit_service import append_audit_log
from app.services.correction_event_service import correction_event_exists, record_correction_event
from app.services.device_command_service import (
    _record_reconciliation_job,
    device_session_lock,
    enqueue_device_command,
    process_command,
)
from app.services.device_attlog_protocol import _ts_match
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported, DeviceFetchError
from app.services.device_service import DeviceService

logger = logging.getLogger(__name__)

_CAPS_PROBE_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_CAPS_PROBE_CACHE_TTL = 300.0

CORRECTION_STATUS_PENDING = "pending"
CORRECTION_STATUS_DEVICE_PENDING = "device_pending"
CORRECTION_STATUS_DEVICE_VERIFYING = "device_verifying"
CORRECTION_STATUS_DEVICE_FAILED = "device_failed"
CORRECTION_STATUS_REIMPORT_PENDING = "reimport_pending"
CORRECTION_STATUS_APPLIED = "applied"
CORRECTION_STATUS_APPLIED_DB_ONLY = "applied_db_only"
CORRECTION_STATUS_FAILED = "failed"

_TERMINAL_STATUSES = frozenset(
    {CORRECTION_STATUS_APPLIED, CORRECTION_STATUS_APPLIED_DB_ONLY, CORRECTION_STATUS_FAILED, CORRECTION_STATUS_DEVICE_FAILED}
)


def load_day_snapshot(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> DayAttendanceSnapshot:
    """Load effective attendance for preview (what users see)."""
    return load_day_snapshot_effective(db, employee=employee, local_date=local_date, settings=settings)


def _validate_correction_times(
    *,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    settings: Settings,
) -> None:
    tz = ZoneInfo(settings.timezone)
    start_local = datetime.combine(local_date, dt_time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    for label, ts in (("check_in", new_check_in), ("check_out", new_check_out)):
        if ts is None:
            continue
        local = ts.astimezone(tz)
        if local < start_local or local >= end_local:
            raise ValueError(f"{label} must fall on {local_date.isoformat()} in configured TIMEZONE.")
    if new_check_out is not None and new_check_out <= new_check_in:
        raise ValueError("check_out must be after check_in.")


def _probe_device_caps(device: DeviceService, settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    try:
        caps = device.probe_attlog_capabilities()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot probe device attlog capabilities (%s).", exc)
        caps = {"tier": "C", "supports_write": False}
    tier = str(caps.get("tier") or "C")
    logger.info("Device attlog capability probe: tier=%s supports_write=%s", tier, caps.get("supports_write"))
    if settings.correction_tier_b_write_enabled and tier == "B":
        caps = dict(caps)
        caps["supports_write"] = True
        caps["supports_full_rewrite"] = True
        logger.info("Tier B attlog write enabled via CORRECTION_TIER_B_WRITE_ENABLED")
    return caps


def _device_supports_attlog_write(caps: dict[str, object]) -> bool:
    return bool(caps.get("supports_write"))


def _iso_ts_list(timestamps: list[datetime]) -> list[str]:
    return [ts.astimezone(ZoneInfo("UTC")).isoformat() for ts in timestamps]


def _build_correct_attendance_payload(
    *,
    correction: AttendanceCorrection,
    employee: Employee,
    delete_timestamps: list[datetime],
    new_check_in: datetime,
    new_check_out: datetime | None,
) -> dict[str, Any]:
    return {
        "correction_uuid": correction.correction_uuid,
        "user_id": str(employee.device_user_id),
        "uid": employee.device_uid,
        "delete_timestamps": _iso_ts_list(delete_timestamps),
        "new_check_in": new_check_in.astimezone(ZoneInfo("UTC")).isoformat(),
        "new_check_out": new_check_out.astimezone(ZoneInfo("UTC")).isoformat() if new_check_out else None,
    }


def _check_correction_drift(
    db: Session,
    *,
    correction: AttendanceCorrection,
    employee: Employee,
    imported_timestamps: list[datetime],
    settings: Settings,
    correlation_id: str | None,
) -> None:
    has_in, has_out = verify_imported_timestamps(
        expected_in=correction.new_check_in,
        expected_out=correction.new_check_out,
        imported_timestamps=imported_timestamps,
        tz_name=settings.timezone,
    )
    if has_in and has_out:
        return
    _record_reconciliation_job(
        db,
        job_type="ATTENDANCE_CORRECTION_DRIFT",
        target_entity=f"employee:{employee.id}:date:{correction.local_date.isoformat()}",
        findings={
            "correction_uuid": correction.correction_uuid,
            "expected_check_in": correction.new_check_in.isoformat() if correction.new_check_in else None,
            "expected_check_out": correction.new_check_out.isoformat() if correction.new_check_out else None,
            "imported_timestamps": [ts.isoformat() for ts in imported_timestamps],
            "has_expected_in": has_in,
            "has_expected_out": has_out,
        },
        correlation_id=correlation_id,
    )


def _invalidate_ai_cache(settings: Settings) -> None:
    try:
        from app.ai.cache.redis_cache import AIResponseCache

        cache = AIResponseCache(settings)
        cache.delete_prefix("ai:management:")
        cache.delete_prefix("ai:report:")
        cache.delete_prefix("ai:copilot:")
        cache.delete_prefix("ai:anomaly:")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI cache invalidation skipped: %s", exc)


def _correction_suppression_timestamps(
    before: DayAttendanceSnapshot,
    *,
    new_check_in: datetime,
    new_check_out: datetime | None,
    tz_name: str,
) -> list[datetime]:
    """Suppress only punches replaced by a correction, not the corrected IN/OUT times."""
    keep = [new_check_in]
    if new_check_out is not None:
        keep.append(new_check_out)
    suppressed: list[datetime] = []
    for ts in before.log_timestamps:
        if any(_ts_match(ts, kept, tz_name=tz_name) for kept in keep):
            continue
        suppressed.append(ts)
    return suppressed


def _finalize_correction(
    db: Session,
    *,
    correction: AttendanceCorrection,
    employee: Employee,
    before: DayAttendanceSnapshot,
    new_check_in: datetime,
    new_check_out: datetime | None,
    settings: Settings,
    final_status: str,
    device_verification_details: dict[str, Any] | None,
    from_device_verify: bool,
    device: DeviceService | None,
    correlation_id: str | None,
    device_operation_uuid: str,
) -> bool:
    """
    Non-destructive finalize: append device events, update effective layer, rebuild sessions.
    Returns False if already finalized (idempotent).
    """
    if correction.status in _TERMINAL_STATUSES:
        return False
    if correction_event_exists(db, correction_uuid=correction.correction_uuid, event_type="finalized"):
        return False

    event = record_correction_event(
        db,
        correction_uuid=correction.correction_uuid,
        event_type="finalized",
        device_operation_uuid=device_operation_uuid,
        payload={"status": final_status, "from_device_verify": from_device_verify},
    )
    if event is None:
        return False

    imported_ts: list[datetime] = []
    if device is not None:
        correction.status = CORRECTION_STATUS_REIMPORT_PENDING
        db.flush()
        _, imported_ts = reimport_attendance_window(
            db,
            employee=employee,
            local_date=correction.local_date,
            device=device,
            settings=settings,
        )
        correction.reimport_completed_at = datetime.now(ZoneInfo("UTC"))

    _insert_sync_suppressions_idempotent(
        db,
        device_id=settings.zk_device_id,
        employee_code=str(employee.device_user_id),
        timestamps=_correction_suppression_timestamps(
            before,
            new_check_in=new_check_in,
            new_check_out=new_check_out,
            tz_name=settings.timezone,
        ),
        correction_id=correction.id,
    )

    apply_correction_to_effective_punches(
        db,
        employee=employee,
        local_date=correction.local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        correction_uuid=correction.correction_uuid,
        settings=settings,
        commit=False,
    )
    rebuild_sessions_for_employee_date(
        db,
        employee_id=employee.id,
        local_date=correction.local_date,
        settings=settings,
        commit=False,
    )

    if device is not None and imported_ts:
        _check_correction_drift(
            db,
            correction=correction,
            employee=employee,
            imported_timestamps=imported_ts,
            settings=settings,
            correlation_id=correlation_id,
        )

    _invalidate_ai_cache(settings)
    correction.status = final_status
    correction.applied_at = datetime.now(ZoneInfo("UTC"))
    correction.error_message = None
    correction.device_operation_uuid = device_operation_uuid
    if device_verification_details is not None:
        correction.device_verification_details = device_verification_details
    return True


def _try_process_correction_command(db: Session, command: DeviceCommand, *, settings: Settings) -> None:
    try:
        process_command(db, command, settings=settings, worker_id="api-inline-correction")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Inline CORRECT_ATTENDANCE processing failed (%s); worker will retry.", exc)


def _enqueue_strict_device_correction(
    db: Session,
    *,
    correction: AttendanceCorrection,
    employee: Employee,
    before: DayAttendanceSnapshot,
    new_check_in: datetime,
    new_check_out: datetime | None,
    actor_user_uuid: str,
    correlation_id: str | None,
    settings: Settings,
    caps: dict[str, object],
) -> AttendanceCorrection:
    record_correction_event(
        db,
        correction_uuid=correction.correction_uuid,
        event_type="requested",
        device_operation_uuid=f"{correction.correction_uuid}:requested",
        payload={"new_check_in": new_check_in.isoformat(), "new_check_out": new_check_out.isoformat() if new_check_out else None},
    )
    payload = _build_correct_attendance_payload(
        correction=correction,
        employee=employee,
        delete_timestamps=before.log_timestamps,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
    )
    command = enqueue_device_command(
        db,
        device_id=settings.zk_device_id,
        command_type="CORRECT_ATTENDANCE",
        payload=payload,
        correlation_id=correlation_id,
        created_by=actor_user_uuid,
        initiated_from="api:attendance_correction",
    )
    correction.device_command_uuid = command.command_uuid
    correction.device_tier = str(caps.get("tier") or "C")[:1]
    correction.correction_mode = "strict_device"
    correction.status = CORRECTION_STATUS_DEVICE_PENDING
    db.commit()
    db.refresh(correction)
    _try_process_correction_command(db, command, settings=settings)
    db.refresh(correction)
    return correction


def apply_attendance_correction(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    actor_user_uuid: str,
    correlation_id: str | None,
    device_service: DeviceService | None = None,
    settings: Settings | None = None,
) -> AttendanceCorrection:
    settings = settings or get_settings()
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise ValueError("Employee not found.")
    if not employee.device_user_id:
        raise ValueError("Employee has no device_user_id.")

    _validate_correction_times(
        local_date=local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        settings=settings,
    )

    with employee_day_lock(employee_id, local_date, settings):
        before = load_day_snapshot(db, employee=employee, local_date=local_date, settings=settings)
        correction = AttendanceCorrection(
            correction_uuid=str(uuid4()),
            employee_id=employee.id,
            local_date=local_date,
            previous_check_in=before.first_check_in,
            previous_check_out=before.last_check_out,
            new_check_in=new_check_in,
            new_check_out=new_check_out,
            actor_user_uuid=actor_user_uuid,
            status=CORRECTION_STATUS_PENDING,
            device_operation_uuid=str(uuid4()),
        )
        db.add(correction)
        db.flush()

        device = device_service or DeviceService(settings=settings)

        cache_key = settings.zk_device_id
        cached = _CAPS_PROBE_CACHE.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _CAPS_PROBE_CACHE_TTL:
            caps = dict(cached[1])
        else:
            with device_session_lock(settings.zk_device_id, settings):
                caps = _probe_device_caps(device, settings)
            _CAPS_PROBE_CACHE[cache_key] = (time.monotonic(), caps)
        tier = str(caps.get("tier") or "C")[:1]
        correction.device_tier = tier
        writable = _device_supports_attlog_write(caps)

        if settings.strict_device_authority:
            correction.correction_mode = "strict_device"
            # Tier B readback fails on this firmware; DB-first avoids queue deadlock and slow retries.
            skip_device_queue = (
                settings.correction_allow_db_only_fallback
                and tier == "B"
                and writable
            )
            if writable and not skip_device_queue:
                return _enqueue_strict_device_correction(
                    db,
                    correction=correction,
                    employee=employee,
                    before=before,
                    new_check_in=new_check_in,
                    new_check_out=new_check_out,
                    actor_user_uuid=actor_user_uuid,
                    correlation_id=correlation_id,
                    settings=settings,
                    caps=caps,
                )
            if skip_device_queue:
                correction.correction_mode = "db_fallback"
                logger.info(
                    "Tier B DB-first path: skipping device queue for correction %s",
                    correction.correction_uuid,
                )
            elif not writable:
                if not settings.correction_allow_db_only_fallback:
                    correction.status = CORRECTION_STATUS_DEVICE_FAILED
                    correction.error_message = (
                        f"Device firmware tier {tier} does not support attlog write; "
                        "strict device authority requires a writable device."
                    )
                    db.commit()
                    db.refresh(correction)
                    return correction
                correction.correction_mode = "db_fallback"

        correction.correction_mode = correction.correction_mode or "db_fallback"
        device_write_skipped = True
        device_verification_details: dict[str, Any] | None = None
        skip_device_attempt = (
            tier == "B"
            and settings.correction_allow_db_only_fallback
            and correction.correction_mode == "db_fallback"
        )

        if not skip_device_attempt:
            with device_session_lock(settings.zk_device_id, settings):
                if writable:
                    try:
                        device_verification_details = device.correct_attendance(
                            user_id=str(employee.device_user_id),
                            uid=employee.device_uid,
                            delete_timestamps=list(before.log_timestamps),
                            new_check_in=new_check_in,
                            new_check_out=new_check_out,
                        )
                        device_write_skipped = False
                        record_correction_event(
                            db,
                            correction_uuid=correction.correction_uuid,
                            event_type="device_write",
                            device_operation_uuid=f"{correction.correction_uuid}:device_write",
                            payload=device_verification_details,
                        )
                    except (AttlogCorrectionNotSupported, AttlogCorrectionError, DeviceFetchError, OSError) as exc:
                        logger.warning("Device attlog correction unavailable (%s); applying effective-only.", exc)
                        device_write_skipped = True

        final_status = (
            CORRECTION_STATUS_APPLIED_DB_ONLY if device_write_skipped else CORRECTION_STATUS_APPLIED
        )
        op_uuid = correction.device_operation_uuid or str(uuid4())
        _finalize_correction(
            db,
            correction=correction,
            employee=employee,
            before=before,
            new_check_in=new_check_in,
            new_check_out=new_check_out,
            settings=settings,
            final_status=final_status,
            device_verification_details=device_verification_details,
            from_device_verify=not device_write_skipped,
            device=device if not device_write_skipped else None,
            correlation_id=correlation_id,
            device_operation_uuid=op_uuid,
        )
        db.commit()
        db.refresh(correction)
        return correction


def finalize_pending_correction_for_command(db: Session, command_uuid: str) -> AttendanceCorrection | None:
    """Apply effective-layer changes after CORRECT_ATTENDANCE device command succeeds."""
    settings = get_settings()
    correction = db.execute(
        select(AttendanceCorrection).where(AttendanceCorrection.device_command_uuid == command_uuid)
    ).scalar_one_or_none()
    if correction is None:
        return None
    if correction.status in _TERMINAL_STATUSES:
        return correction

    employee = db.get(Employee, correction.employee_id)
    if employee is None:
        return None
    if correction.new_check_in is None:
        correction.status = CORRECTION_STATUS_FAILED
        correction.error_message = "Correction record is missing new_check_in."
        db.commit()
        return correction

    command = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)
    ).scalar_one_or_none()
    if command is None or command.status != DeviceCommandStatus.SUCCESS.value:
        return correction

    device_verification_details = command.verification_details if command else None
    before = load_day_snapshot(db, employee=employee, local_date=correction.local_date, settings=settings)
    device = DeviceService(settings=settings)
    op_uuid = correction.device_operation_uuid or f"{correction.correction_uuid}:finalize:{command_uuid}"

    with employee_day_lock(employee.id, correction.local_date, settings):
        with device_session_lock(settings.zk_device_id, settings):
            finalized = _finalize_correction(
                db,
                correction=correction,
                employee=employee,
                before=before,
                new_check_in=correction.new_check_in,
                new_check_out=correction.new_check_out,
                settings=settings,
                final_status=CORRECTION_STATUS_APPLIED,
                device_verification_details=device_verification_details,
                from_device_verify=True,
                device=device,
                correlation_id=command.correlation_id if command else None,
                device_operation_uuid=op_uuid,
            )
            if finalized:
                append_audit_log(
                    db,
                    actor_user_uuid=correction.actor_user_uuid,
                    action_type="ATTENDANCE_ADJUST",
                    entity_type="attendance_correction",
                    entity_id=correction.correction_uuid,
                    previous_state={
                        "check_in": correction.previous_check_in.isoformat() if correction.previous_check_in else None,
                        "check_out": correction.previous_check_out.isoformat() if correction.previous_check_out else None,
                    },
                    new_state={
                        "check_in": correction.new_check_in.isoformat() if correction.new_check_in else None,
                        "check_out": correction.new_check_out.isoformat() if correction.new_check_out else None,
                        "local_date": correction.local_date.isoformat(),
                        "employee_id": correction.employee_id,
                        "correction_mode": correction.correction_mode,
                    },
                    request_id=command.correlation_id if command else None,
                )
            db.commit()
            db.refresh(correction)
            return correction


def mark_correction_failed_for_command(
    db: Session,
    *,
    command_uuid: str,
    error_message: str,
) -> AttendanceCorrection | None:
    settings = get_settings()
    correction = db.execute(
        select(AttendanceCorrection).where(
            AttendanceCorrection.device_command_uuid == command_uuid,
            AttendanceCorrection.status.in_(
                (CORRECTION_STATUS_DEVICE_PENDING, CORRECTION_STATUS_DEVICE_VERIFYING, CORRECTION_STATUS_REIMPORT_PENDING)
            ),
        )
    ).scalar_one_or_none()
    if correction is None:
        return None

    if settings.correction_allow_db_only_fallback and correction.new_check_in is not None:
        employee = db.get(Employee, correction.employee_id)
        if employee is not None:
            before = load_day_snapshot(db, employee=employee, local_date=correction.local_date, settings=settings)
            op_uuid = correction.device_operation_uuid or f"{correction.correction_uuid}:db_fallback:{command_uuid}"
            with employee_day_lock(employee.id, correction.local_date, settings):
                finalized = _finalize_correction(
                    db,
                    correction=correction,
                    employee=employee,
                    before=before,
                    new_check_in=correction.new_check_in,
                    new_check_out=correction.new_check_out,
                    settings=settings,
                    final_status=CORRECTION_STATUS_APPLIED_DB_ONLY,
                    device_verification_details={"device_error": error_message[:500], "fallback": "db_only"},
                    from_device_verify=False,
                    device=None,
                    correlation_id=None,
                    device_operation_uuid=op_uuid,
                )
                if finalized:
                    correction.correction_mode = correction.correction_mode or "db_fallback"
                    correction.error_message = f"Device write failed; applied DB-only fallback. {error_message[:1500]}"
                    record_correction_event(
                        db,
                        correction_uuid=correction.correction_uuid,
                        event_type="device_failed",
                        device_operation_uuid=f"{correction.correction_uuid}:failed:{command_uuid}",
                        payload={"error": error_message[:2000], "db_fallback_applied": True},
                    )
                    db.commit()
                    db.refresh(correction)
                    return correction

    correction.status = CORRECTION_STATUS_DEVICE_FAILED
    correction.error_message = error_message[:2000]
    record_correction_event(
        db,
        correction_uuid=correction.correction_uuid,
        event_type="device_failed",
        device_operation_uuid=f"{correction.correction_uuid}:failed:{command_uuid}",
        payload={"error": error_message[:2000]},
    )
    db.flush()
    return correction


def recover_orphan_correction(db: Session, correction: AttendanceCorrection) -> AttendanceCorrection:
    """
    Finalize corrections stuck in pending without a device command (e.g. failed enqueue).
    Applies DB-only fallback when enabled.
    """
    settings = get_settings()
    if correction.status not in (CORRECTION_STATUS_PENDING, CORRECTION_STATUS_DEVICE_PENDING):
        return correction
    if correction.device_command_uuid:
        return correction
    if correction.new_check_in is None:
        correction.status = CORRECTION_STATUS_FAILED
        correction.error_message = "Orphan correction missing new_check_in."
        db.flush()
        return correction
    if not settings.correction_allow_db_only_fallback:
        correction.status = CORRECTION_STATUS_FAILED
        correction.error_message = "Orphan correction; DB-only fallback disabled."
        db.flush()
        return correction

    employee = db.get(Employee, correction.employee_id)
    if employee is None:
        correction.status = CORRECTION_STATUS_FAILED
        correction.error_message = "Orphan correction: employee not found."
        db.flush()
        return correction

    before = load_day_snapshot(db, employee=employee, local_date=correction.local_date, settings=settings)
    op_uuid = correction.device_operation_uuid or f"{correction.correction_uuid}:orphan_recovery"
    with employee_day_lock(employee.id, correction.local_date, settings):
        finalized = _finalize_correction(
            db,
            correction=correction,
            employee=employee,
            before=before,
            new_check_in=correction.new_check_in,
            new_check_out=correction.new_check_out,
            settings=settings,
            final_status=CORRECTION_STATUS_APPLIED_DB_ONLY,
            device_verification_details={"orphan_recovery": True},
            from_device_verify=False,
            device=None,
            correlation_id=None,
            device_operation_uuid=op_uuid,
        )
        if finalized:
            correction.correction_mode = correction.correction_mode or "db_fallback"
            correction.error_message = "Recovered orphan correction via DB-only fallback."
    db.flush()
    return correction


def probe_correction_capabilities(
    device_service: DeviceService | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    cache_key = settings.zk_device_id
    now = time.monotonic()
    cached = _CAPS_PROBE_CACHE.get(cache_key)
    if cached is not None and now - cached[0] < _CAPS_PROBE_CACHE_TTL:
        return dict(cached[1])

    device = device_service or DeviceService(settings=settings)
    with device_session_lock(settings.zk_device_id, settings):
        caps = _probe_device_caps(device, settings)
    result = {
        **caps,
        "strict_device_authority": settings.strict_device_authority,
        "correction_allow_db_only_fallback": settings.correction_allow_db_only_fallback,
    }
    _CAPS_PROBE_CACHE[cache_key] = (now, result)
    return result
