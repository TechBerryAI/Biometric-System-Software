"""Repair punches stamped ~12h behind because the terminal was on the wrong AM/PM."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.app_timezone import UTC, as_aware, local_date, to_utc
from app.core.config import Settings, get_settings
from app.domains.attendance.models.attendance_ingest_skip import AttendanceIngestSkip
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_helpers import rebuild_sessions_for_employee_date
from app.domains.employees.models.employee import Employee

IST = ZoneInfo("Asia/Kolkata")
INCIDENT_START_IST = datetime(2026, 8, 21, 16, 0, tzinfo=IST)
LAG_MIN = timedelta(hours=11, minutes=30)
LAG_MAX = timedelta(hours=16)
SHIFT = timedelta(hours=12)


@dataclass
class ClockShiftRepairReport:
    matched: int = 0
    updated: int = 0
    deleted_duplicates: int = 0
    skip_rows: int = 0
    sessions_rebuilt: int = 0
    employee_days: list[str] = field(default_factory=list)
    dry_run: bool = True


def _insert_lag(log: AttendanceLog) -> timedelta:
    created = as_aware(log.created_at, UTC)
    stamped = as_aware(log.timestamp, UTC)
    return created - stamped


def select_twelve_hour_shift_logs(
    db: Session,
    *,
    incident_start: datetime = INCIDENT_START_IST,
) -> list[AttendanceLog]:
    """Logs whose insert time is 11.5–16h after the device stamp (AM/PM error, including delayed re-pulls)."""
    start_utc = as_aware(incident_start, IST).astimezone(UTC)
    rows = list(
        db.execute(select(AttendanceLog).where(AttendanceLog.created_at >= start_utc)).scalars().all()
    )
    return [row for row in rows if LAG_MIN <= _insert_lag(row) <= LAG_MAX]


def ingest_skip_key(employee_code: str, timestamp: datetime, punch_type: str) -> tuple[str, str, str]:
    stamp = as_aware(timestamp, UTC).astimezone(UTC)
    return (str(employee_code), stamp.isoformat(), str(punch_type))


def load_ingest_skip_keys(db: Session, device_id: str) -> set[tuple[str, str, str]]:
    rows = db.execute(
        select(
            AttendanceIngestSkip.employee_code,
            AttendanceIngestSkip.timestamp,
            AttendanceIngestSkip.punch_type,
        ).where(AttendanceIngestSkip.device_id == device_id)
    ).all()
    return {ingest_skip_key(code, ts, punch) for code, ts, punch in rows}


def record_ingest_skip(
    db: Session,
    *,
    device_id: str,
    employee_code: str,
    original_timestamp: datetime,
    punch_type: str,
    repaired_timestamp: datetime,
) -> bool:
    """Return True when a new skip row is inserted."""
    existing = db.execute(
        select(AttendanceIngestSkip.id).where(
            AttendanceIngestSkip.device_id == device_id,
            AttendanceIngestSkip.employee_code == employee_code,
            AttendanceIngestSkip.timestamp == as_aware(original_timestamp, UTC).astimezone(UTC),
            AttendanceIngestSkip.punch_type == punch_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        AttendanceIngestSkip(
            device_id=device_id,
            employee_code=employee_code,
            timestamp=as_aware(original_timestamp, UTC).astimezone(UTC),
            punch_type=punch_type,
            repaired_timestamp=as_aware(repaired_timestamp, UTC).astimezone(UTC),
        )
    )
    return True


def purge_reimported_skipped_logs(
    db: Session,
    *,
    employees: dict[str, Employee],
    tz: ZoneInfo,
) -> tuple[int, set[tuple[int, datetime]]]:
    """Delete logs whose timestamp still matches a recorded original (stale full-sync copies)."""
    skips = list(db.execute(select(AttendanceIngestSkip)).scalars().all())
    deleted = 0
    affected: set[tuple[int, datetime]] = set()
    for skip in skips:
        row = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.device_id == skip.device_id,
                AttendanceLog.employee_code == skip.employee_code,
                AttendanceLog.timestamp == skip.timestamp,
                AttendanceLog.punch_type == skip.punch_type,
            )
        ).scalar_one_or_none()
        if row is None:
            continue
        emp = employees.get(str(row.employee_code))
        if emp is not None:
            affected.add((emp.id, local_date(row.timestamp, tz)))
            affected.add((emp.id, local_date(skip.repaired_timestamp, tz)))
        db.delete(row)
        deleted += 1
    return deleted, affected


def repair_twelve_hour_clock_shift(
    db: Session,
    *,
    apply: bool = False,
    settings: Settings | None = None,
    incident_start: datetime = INCIDENT_START_IST,
) -> ClockShiftRepairReport:
    """Shift incident-window AM/PM stamps forward 12 hours and record ingest skips."""
    settings = settings or get_settings()
    tz = ZoneInfo(settings.resolved_timezone())
    logs = select_twelve_hour_shift_logs(db, incident_start=incident_start)
    report = ClockShiftRepairReport(matched=len(logs), dry_run=not apply)
    employees = {
        str(emp.device_user_id): emp
        for emp in db.execute(select(Employee)).scalars().all()
        if emp.device_user_id
    }
    affected: set[tuple[int, datetime]] = set()

    if apply:
        purged, purged_days = purge_reimported_skipped_logs(db, employees=employees, tz=tz)
        report.deleted_duplicates += purged
        affected.update(purged_days)

    for log in logs:
        if apply and sa_inspect(log).deleted:
            continue
        original = as_aware(log.timestamp, UTC).astimezone(UTC)
        repaired = original + SHIFT
        if apply:
            inserted = record_ingest_skip(
                db,
                device_id=log.device_id,
                employee_code=log.employee_code,
                original_timestamp=original,
                punch_type=log.punch_type,
                repaired_timestamp=repaired,
            )
            if inserted:
                report.skip_rows += 1
            duplicate = db.execute(
                select(AttendanceLog).where(
                    AttendanceLog.device_id == log.device_id,
                    AttendanceLog.employee_code == log.employee_code,
                    AttendanceLog.punch_type == log.punch_type,
                    AttendanceLog.timestamp == repaired,
                    AttendanceLog.id != log.id,
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                db.delete(log)
                report.deleted_duplicates += 1
            else:
                log.timestamp = repaired
                report.updated += 1
        emp = employees.get(str(log.employee_code))
        if emp is None:
            continue
        for day in (local_date(original, tz), local_date(repaired, tz)):
            affected.add((emp.id, day))

    report.employee_days = sorted(f"{emp_id}:{day.isoformat()}" for emp_id, day in affected)
    if apply:
        db.flush()
        rebuilt = 0
        for employee_id, day in sorted(affected):
            rebuilt += rebuild_sessions_for_employee_date(
                db, employee_id=employee_id, local_date=day, settings=settings, commit=False
            )
        report.sessions_rebuilt = rebuilt
        db.commit()
    return report


def fetched_record_is_skipped(
    *,
    employee_code: str,
    timestamp: datetime,
    punch_type: str,
    skip_keys: set[tuple[str, str, str]],
    tz: ZoneInfo,
) -> bool:
    stamp = to_utc(timestamp, tz)
    return ingest_skip_key(employee_code, stamp, punch_type) in skip_keys
