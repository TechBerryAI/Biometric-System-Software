"""Attendance correction: verified F22 attlog write, then replace attendance_logs in place."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core import device_policy
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.employee import Employee
from app.services.attendance_helpers import (
    DayAttendanceSnapshot,
    load_day_snapshot,
    rebuild_sessions_for_employee_date,
    replace_employee_day_logs,
)
from app.services.attendance_lock_service import employee_day_lock
from app.services.device_command_service import (
    device_session_lock,
    enqueue_device_command,
    process_command,
)
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported
from app.services.device_service import DeviceService

logger = logging.getLogger(__name__)

_CAPS_PROBE_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_CAPS_PROBE_CACHE_TTL = 300.0

CORRECTION_STATUS_DEVICE_PENDING = "device_pending"
CORRECTION_STATUS_APPLIED = "applied"
CORRECTION_STATUS_DEVICE_FAILED = "device_failed"
CORRECTION_STATUS_FAILED = "failed"


@dataclass
class AttendanceAdjustmentResult:
    """Result of an attendance correction (no ledger table)."""

    employee_id: int
    local_date: date
    previous_check_in: datetime | None
    previous_check_out: datetime | None
    new_check_in: datetime | None
    new_check_out: datetime | None
    status: str
    device_updated: bool
    device_command_uuid: str | None
    device_tier: str | None
    error_message: str | None
    applied_at: datetime | None


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
    if device_policy.ATTLOG_TIER_B_REWRITE and tier == "B":
        caps = dict(caps)
        caps["supports_write"] = True
        caps["supports_full_rewrite"] = True
        logger.info("Tier B attlog rewrite allowed by internal policy")
    return caps


def _device_supports_attlog_write(caps: dict[str, object]) -> bool:
    return bool(caps.get("supports_write"))


def _iso_ts_list(timestamps: list[datetime]) -> list[str]:
    return [ts.astimezone(ZoneInfo("UTC")).isoformat() for ts in timestamps]


def _build_correct_attendance_payload(
    *,
    employee: Employee,
    local_date: date,
    delete_timestamps: list[datetime],
    new_check_in: datetime,
    new_check_out: datetime | None,
) -> dict[str, Any]:
    return {
        "employee_id": employee.id,
        "local_date": local_date.isoformat(),
        "user_id": str(employee.device_user_id),
        "uid": employee.device_uid,
        "delete_timestamps": _iso_ts_list(delete_timestamps),
        "new_check_in": new_check_in.astimezone(ZoneInfo("UTC")).isoformat(),
        "new_check_out": new_check_out.astimezone(ZoneInfo("UTC")).isoformat() if new_check_out else None,
    }


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


def _apply_db_replacement(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    settings: Settings,
) -> None:
    replace_employee_day_logs(
        db,
        employee=employee,
        local_date=local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        device_id=settings.zk_device_id,
        settings=settings,
    )
    rebuild_sessions_for_employee_date(
        db,
        employee_id=employee.id,
        local_date=local_date,
        settings=settings,
        commit=False,
    )
    _invalidate_ai_cache(settings)


def _try_process_correction_command(db: Session, command: DeviceCommand, *, settings: Settings) -> None:
    try:
        process_command(db, command, settings=settings, worker_id="api-inline-correction")
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Inline CORRECT_ATTENDANCE processing failed (%s); worker will retry.", exc)


def _parse_payload_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def finalize_pending_correction_for_command(db: Session, command_uuid: str) -> AttendanceAdjustmentResult | None:
    """Replace attendance_logs after CORRECT_ATTENDANCE device command succeeds."""
    settings = get_settings()
    command = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)
    ).scalar_one_or_none()
    if command is None or command.status != DeviceCommandStatus.SUCCESS.value:
        return None
    if command.command_type != "CORRECT_ATTENDANCE":
        return None

    payload = command.payload or {}
    employee_id = payload.get("employee_id")
    local_date_raw = payload.get("local_date")
    new_check_in = _parse_payload_datetime(payload.get("new_check_in"))
    new_check_out = _parse_payload_datetime(payload.get("new_check_out"))
    if employee_id is None or local_date_raw is None or new_check_in is None:
        return None

    employee = db.get(Employee, int(employee_id))
    if employee is None:
        return None
    local_date = date.fromisoformat(str(local_date_raw))
    before = load_day_snapshot(db, employee=employee, local_date=local_date, settings=settings)

    with employee_day_lock(employee.id, local_date, settings):
        _apply_db_replacement(
            db,
            employee=employee,
            local_date=local_date,
            new_check_in=new_check_in,
            new_check_out=new_check_out,
            settings=settings,
        )
        db.commit()

    applied_at = datetime.now(ZoneInfo("UTC"))
    return AttendanceAdjustmentResult(
        employee_id=employee.id,
        local_date=local_date,
        previous_check_in=before.first_check_in,
        previous_check_out=before.last_check_out,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        status=CORRECTION_STATUS_APPLIED,
        device_updated=True,
        device_command_uuid=command_uuid,
        device_tier=None,
        error_message=None,
        applied_at=applied_at,
    )


def mark_correction_failed_for_command(
    db: Session,
    *,
    command_uuid: str,
    error_message: str,
) -> None:
    """Record device failure on the command only — never mutate attendance_logs without device write."""
    command = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)
    ).scalar_one_or_none()
    if command is None:
        return
    if command.status not in (
        DeviceCommandStatus.FAILED.value,
        DeviceCommandStatus.DEAD_LETTER.value,
    ):
        command.status = DeviceCommandStatus.FAILED.value
        command.completed_at = datetime.now(ZoneInfo("UTC"))
    command.last_error = (error_message or command.last_error or "Device attlog correction failed.")[:2000]
    db.flush()


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
) -> AttendanceAdjustmentResult:
    """
    Device-first correction: require verified attlog write, then replace day logs.
    Never applies DB-only changes when the device cannot write.
    """
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
        writable = _device_supports_attlog_write(caps)
        if not writable:
            raise AttlogCorrectionNotSupported(
                f"Device firmware tier {tier} does not support attlog write. "
                "Use a Tier A device, or enable Tier B rewrite in internal device policy. "
                "Corrections require a verified device write so sync does not restore old punches."
            )

        payload = _build_correct_attendance_payload(
            employee=employee,
            local_date=local_date,
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
        db.commit()
        db.refresh(command)

        _try_process_correction_command(db, command, settings=settings)
        db.refresh(command)

        if command.status == DeviceCommandStatus.SUCCESS.value:
            result = finalize_pending_correction_for_command(db, command.command_uuid)
            if result is not None:
                result.device_tier = tier
                return result
            # finalize already ran during process_command — rebuild result from logs
            after = load_day_snapshot(db, employee=employee, local_date=local_date, settings=settings)
            return AttendanceAdjustmentResult(
                employee_id=employee.id,
                local_date=local_date,
                previous_check_in=before.first_check_in,
                previous_check_out=before.last_check_out,
                new_check_in=after.first_check_in or new_check_in,
                new_check_out=after.last_check_out if after.last_check_out is not None else new_check_out,
                status=CORRECTION_STATUS_APPLIED,
                device_updated=True,
                device_command_uuid=command.command_uuid,
                device_tier=tier,
                error_message=None,
                applied_at=datetime.now(ZoneInfo("UTC")),
            )

        if command.status in (
            DeviceCommandStatus.PENDING.value,
            DeviceCommandStatus.RUNNING.value,
            DeviceCommandStatus.RETRYING.value,
            DeviceCommandStatus.VERIFYING.value,
        ):
            return AttendanceAdjustmentResult(
                employee_id=employee.id,
                local_date=local_date,
                previous_check_in=before.first_check_in,
                previous_check_out=before.last_check_out,
                new_check_in=new_check_in,
                new_check_out=new_check_out,
                status=CORRECTION_STATUS_DEVICE_PENDING,
                device_updated=False,
                device_command_uuid=command.command_uuid,
                device_tier=tier,
                error_message=None,
                applied_at=None,
            )

        err = command.last_error or "Device attlog correction failed."
        raise AttlogCorrectionError(err)


def get_adjustment_command_status(
    db: Session,
    *,
    command_uuid: str,
) -> AttendanceAdjustmentResult | None:
    """Status of a correction command (replaces correction_uuid ledger lookup)."""
    command = db.execute(
        select(DeviceCommand).where(
            DeviceCommand.command_uuid == command_uuid,
            DeviceCommand.command_type == "CORRECT_ATTENDANCE",
        )
    ).scalar_one_or_none()
    if command is None:
        return None
    payload = command.payload or {}
    employee_id = int(payload.get("employee_id") or 0)
    local_date_raw = payload.get("local_date")
    local_date = date.fromisoformat(str(local_date_raw)) if local_date_raw else date.today()
    new_check_in = _parse_payload_datetime(payload.get("new_check_in"))
    new_check_out = _parse_payload_datetime(payload.get("new_check_out"))

    if command.status == DeviceCommandStatus.SUCCESS.value:
        status = CORRECTION_STATUS_APPLIED
        device_updated = True
        error_message = None
        applied_at = command.completed_at
    elif command.status in (
        DeviceCommandStatus.PENDING.value,
        DeviceCommandStatus.RUNNING.value,
        DeviceCommandStatus.RETRYING.value,
        DeviceCommandStatus.VERIFYING.value,
    ):
        status = CORRECTION_STATUS_DEVICE_PENDING
        device_updated = False
        error_message = None
        applied_at = None
    else:
        status = CORRECTION_STATUS_DEVICE_FAILED
        device_updated = False
        error_message = command.last_error
        applied_at = command.completed_at

    return AttendanceAdjustmentResult(
        employee_id=employee_id,
        local_date=local_date,
        previous_check_in=None,
        previous_check_out=None,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        status=status,
        device_updated=device_updated,
        device_command_uuid=command.command_uuid,
        device_tier=None,
        error_message=error_message,
        applied_at=applied_at,
    )


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
        "strict_device_authority": True,
        "correction_allow_db_only_fallback": False,
    }
    _CAPS_PROBE_CACHE[cache_key] = (now, result)
    return result
