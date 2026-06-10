"""GOD-mode attendance correction: device + database atomic rewrite."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_correction import AttendanceCorrection
from app.models.attendance_log import AttendanceLog
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.device_command import DeviceCommandStatus
from app.models.employee import Employee
from app.services.attendance_service import _resolve_mapping_for_punch, rebuild_sessions_for_local_date
from app.services.device_command_service import enqueue_device_command, process_command
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported
from app.services.device_service import DeviceService
from app.services.employee_identity import identity_filter_for_employee
from app.services.punch_classification import classify_punch

logger = logging.getLogger(__name__)

PUNCH_IN = "0"
PUNCH_OUT = "1"


@dataclass(frozen=True, slots=True)
class DayAttendanceSnapshot:
    local_date: date
    first_check_in: datetime | None
    last_check_out: datetime | None
    log_ids: list[int]
    log_timestamps: list[datetime]


def _day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def load_day_snapshot(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> DayAttendanceSnapshot:
    cfg = settings or get_settings()
    start_utc, end_utc = _day_bounds_utc(local_date, cfg.timezone)
    logs = list(
        db.execute(
            select(AttendanceLog)
            .where(
                identity_filter_for_employee(employee, db),
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
            )
            .order_by(AttendanceLog.timestamp)
        ).scalars().all()
    )
    ins = [x.timestamp for x in logs if classify_punch(x.punch_type) is True]
    outs = [x.timestamp for x in logs if classify_punch(x.punch_type) is False]
    first_in = min(ins) if ins else (logs[0].timestamp if logs else None)
    last_out = max(outs) if outs else (logs[-1].timestamp if len(logs) > 1 else None)
    return DayAttendanceSnapshot(
        local_date=local_date,
        first_check_in=first_in,
        last_check_out=last_out,
        log_ids=[lg.id for lg in logs],
        log_timestamps=[lg.timestamp for lg in logs],
    )


def _validate_correction_times(
    *,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    settings: Settings,
) -> None:
    tz = ZoneInfo(settings.timezone)
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    for label, ts in (("check_in", new_check_in), ("check_out", new_check_out)):
        if ts is None:
            continue
        local = ts.astimezone(tz)
        if local < start_local or local >= end_local:
            raise ValueError(f"{label} must fall on {local_date.isoformat()} in configured TIMEZONE.")
    if new_check_out is not None and new_check_out <= new_check_in:
        raise ValueError("check_out must be after check_in.")


def _device_supports_attlog_write(device: DeviceService) -> bool:
    try:
        caps = device.probe_attlog_capabilities()
        return bool(caps.get("supports_write"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot probe device attlog capabilities (%s); DB-only correction.", exc)
        return False


def _apply_db_correction(
    db: Session,
    *,
    correction: AttendanceCorrection,
    employee: Employee,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    delete_log_ids: list[int],
    delete_timestamps: list[datetime],
    settings: Settings,
    final_status: str = "applied",
) -> None:
    if delete_log_ids:
        db.execute(delete(AttendanceLog).where(AttendanceLog.id.in_(delete_log_ids)))

    for ts in delete_timestamps:
        db.add(
            AttendanceSyncSuppression(
                device_id=settings.zk_device_id,
                employee_code=str(employee.device_user_id),
                suppressed_timestamp=ts,
                reason="correction",
                correction_id=correction.id,
            )
        )

    mapping = None
    for punch_type, ts in ((PUNCH_IN, new_check_in), (PUNCH_OUT, new_check_out)):
        if ts is None:
            continue
        if mapping is None:
            mapping = _resolve_mapping_for_punch(
                db,
                device_id=settings.zk_device_id,
                device_user_id=str(employee.device_user_id),
                at_time=ts,
            )
        db.add(
            AttendanceLog(
                employee_code=str(employee.device_user_id),
                timestamp=ts,
                device_id=settings.zk_device_id,
                employee_uuid=employee.employee_uuid,
                device_mapping_id=mapping.id if mapping else None,
                punch_type=punch_type,
                created_at=ts,
            )
        )

    rebuild_sessions_for_local_date(db, local_date, settings=settings)

    try:
        from app.ai.cache.redis_cache import AIResponseCache

        cache = AIResponseCache(settings)
        cache.delete_prefix("ai:management:")
        cache.delete_prefix("ai:report:")
        cache.delete_prefix("ai:copilot:")
        cache.delete_prefix("ai:anomaly:")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI cache invalidation skipped: %s", exc)

    correction.status = final_status
    correction.applied_at = datetime.now(ZoneInfo("UTC"))
    correction.error_message = None


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
        status="pending",
    )
    db.add(correction)
    db.flush()

    device = device_service or DeviceService(settings=settings)
    device_write_skipped = False
    if _device_supports_attlog_write(device):
        try:
            device.correct_attendance(
                user_id=str(employee.device_user_id),
                uid=employee.device_uid,
                delete_timestamps=list(before.log_timestamps),
                new_check_in=new_check_in,
                new_check_out=new_check_out,
            )
        except (AttlogCorrectionNotSupported, AttlogCorrectionError) as exc:
            logger.warning("Device attlog correction unavailable (%s); applying DB-only.", exc)
            device_write_skipped = True
    else:
        logger.info(
            "Device firmware does not support attlog write (employee=%s date=%s); DB-only correction.",
            employee.id,
            local_date.isoformat(),
        )
        device_write_skipped = True

    _apply_db_correction(
        db,
        correction=correction,
        employee=employee,
        local_date=local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        delete_log_ids=before.log_ids,
        delete_timestamps=before.log_timestamps,
        settings=settings,
        final_status="applied_db_only" if device_write_skipped else "applied",
    )
    db.commit()
    db.refresh(correction)
    return correction


def apply_attendance_correction_via_command(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    actor_user_uuid: str,
    correlation_id: str | None,
    initiated_from: str = "api:attendance.god.correct",
) -> AttendanceCorrection:
    settings = get_settings()
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise ValueError("Employee not found.")

    before = load_day_snapshot(db, employee=employee, local_date=local_date, settings=settings)
    _validate_correction_times(
        local_date=local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        settings=settings,
    )

    correction = AttendanceCorrection(
        correction_uuid=str(uuid4()),
        employee_id=employee.id,
        local_date=local_date,
        previous_check_in=before.first_check_in,
        previous_check_out=before.last_check_out,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        actor_user_uuid=actor_user_uuid,
        status="pending",
    )
    db.add(correction)
    db.flush()

    payload = {
        "user_id": str(employee.device_user_id),
        "uid": employee.device_uid,
        "delete_timestamps": [ts.isoformat() for ts in before.log_timestamps],
        "new_check_in": new_check_in.isoformat(),
        "new_check_out": new_check_out.isoformat() if new_check_out else None,
    }
    command = enqueue_device_command(
        db,
        device_id=settings.zk_device_id,
        command_type="CORRECT_ATTENDANCE",
        payload=payload,
        correlation_id=correlation_id,
        created_by=actor_user_uuid,
        initiated_from=initiated_from,
    )
    correction.device_command_uuid = command.command_uuid
    db.commit()

    process_command(db, command, settings=settings, worker_id="api-inline")
    # Commit command terminal status before checking outcome. Do not refresh here:
    # refresh would reload the pre-process PENDING row and leave the command stuck.
    db.commit()

    if command.status != DeviceCommandStatus.SUCCESS.value:
        correction.status = "failed"
        correction.error_message = command.last_error or f"Device command ended with status {command.status}"
        db.commit()
        raise AttlogCorrectionError(correction.error_message or "Device correction failed.")

    _apply_db_correction(
        db,
        correction=correction,
        employee=employee,
        local_date=local_date,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
        delete_log_ids=before.log_ids,
        delete_timestamps=before.log_timestamps,
        settings=settings,
    )
    db.commit()
    db.refresh(correction)
    return correction


def finalize_pending_correction_for_command(db: Session, command_uuid: str) -> AttendanceCorrection | None:
    """Apply DB changes for a correction whose device command completed after an earlier failure."""
    settings = get_settings()
    correction = db.execute(
        select(AttendanceCorrection).where(
            AttendanceCorrection.device_command_uuid == command_uuid,
            AttendanceCorrection.status.in_(("pending", "failed")),
        )
    ).scalar_one_or_none()
    if correction is None:
        return None
    employee = db.get(Employee, correction.employee_id)
    if employee is None:
        return None
    before = load_day_snapshot(db, employee=employee, local_date=correction.local_date, settings=settings)
    if correction.new_check_in is None:
        correction.status = "failed"
        correction.error_message = "Correction record is missing new_check_in."
        db.commit()
        return correction
    _apply_db_correction(
        db,
        correction=correction,
        employee=employee,
        local_date=correction.local_date,
        new_check_in=correction.new_check_in,
        new_check_out=correction.new_check_out,
        delete_log_ids=before.log_ids,
        delete_timestamps=before.log_timestamps,
        settings=settings,
    )
    db.commit()
    db.refresh(correction)
    return correction
