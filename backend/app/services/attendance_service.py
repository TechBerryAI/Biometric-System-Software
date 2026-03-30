"""User sync, attendance log sync, and session pairing logic."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser

logger = logging.getLogger(__name__)

def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def _minutes_late(check_in: datetime, shift_start: time | None, tz: ZoneInfo) -> int | None:
    if shift_start is None:
        return None
    local = check_in.astimezone(tz)
    expected = datetime.combine(local.date(), shift_start, tzinfo=tz)
    delta = local - expected
    secs = int(delta.total_seconds())
    return max(0, secs // 60) if secs > 0 else 0


def _minutes_early(check_out: datetime, shift_end: time | None, tz: ZoneInfo) -> int | None:
    if shift_end is None:
        return None
    local = check_out.astimezone(tz)
    expected = datetime.combine(local.date(), shift_end, tzinfo=tz)
    delta = expected - local
    secs = int(delta.total_seconds())
    return max(0, secs // 60) if secs > 0 else 0


def _classify_punch(punch_type: str) -> bool | None:
    """True = check-in, False = check-out, None = unknown."""
    p = punch_type.strip().lower()
    if p in ("0", "in", "check_in", "i"):
        return True
    if p in ("1", "out", "check_out", "o"):
        return False
    return None


def sync_employees_from_device_users(db: Session, users: Sequence[DeviceUser]) -> int:
    """
    Upsert device users into employees with ON CONFLICT DO NOTHING on device_user_id.
    Returns number of rows attempted (not necessarily inserted).
    """
    inserted = 0
    for u in users:
        stmt = (
            pg_insert(Employee)
            .values(
                device_user_id=u.uid,
                name=u.name,
                department=None,
                shift_start=None,
                shift_end=None,
            )
            .on_conflict_do_nothing(index_elements=[Employee.device_user_id])
        )
        result = db.execute(stmt)
        rc = result.rowcount
        # psycopg may return -1 for "unknown" on INSERT ... ON CONFLICT DO NOTHING
        if rc is not None and rc > 0:
            inserted += rc
    db.commit()
    return inserted


def insert_attendance_logs_idempotent(
    db: Session,
    records: Sequence[DeviceAttendanceRecord],
    device_id: str,
) -> int:
    """Insert raw logs; duplicates ignored via unique (employee_code, timestamp)."""
    rows = 0
    for r in records:
        employee_code = str(r.user_id)
        punch_type = str(r.punch)
        stmt = (
            pg_insert(AttendanceLog)
            .values(
                employee_code=employee_code,
                timestamp=r.timestamp,
                device_id=device_id,
                punch_type=punch_type,
            )
            .on_conflict_do_nothing(constraint="uq_log_employee_ts")
        )
        res = db.execute(stmt)
        rc = res.rowcount
        if rc is not None and rc > 0:
            rows += rc
    db.commit()
    return rows


def _pair_logs_for_day(
    logs: list[AttendanceLog],
    _tz: ZoneInfo,
) -> list[tuple[AttendanceLog, AttendanceLog | None, str]]:
    """
    Pair IN/OUT for one employee for one local calendar day.
    Returns list of (check_in_log, check_out_log_or_none, status).
    """
    logs_sorted = sorted(logs, key=lambda x: x.timestamp)
    sessions: list[tuple[AttendanceLog, AttendanceLog | None, str]] = []
    pending_in: AttendanceLog | None = None
    next_expects_in = True

    for log in logs_sorted:
        cls = _classify_punch(log.punch_type)
        if cls is True:
            if pending_in is not None:
                sessions.append((pending_in, None, "missing_check_out"))
            pending_in = log
            next_expects_in = False
        elif cls is False:
            if pending_in is None:
                continue
            if log.timestamp <= pending_in.timestamp:
                continue
            sessions.append((pending_in, log, "complete"))
            pending_in = None
            next_expects_in = True
        else:
            if next_expects_in:
                if pending_in is not None:
                    sessions.append((pending_in, None, "missing_check_out"))
                pending_in = log
                next_expects_in = False
            else:
                if pending_in is None:
                    next_expects_in = True
                    continue
                if log.timestamp <= pending_in.timestamp:
                    continue
                sessions.append((pending_in, log, "complete"))
                pending_in = None
                next_expects_in = True

    if pending_in is not None:
        sessions.append((pending_in, None, "missing_check_out"))

    return sessions


def rebuild_sessions_for_local_date(db: Session, target: date, settings: Settings | None = None) -> int:
    """
    Recompute AttendanceSession rows for all employees for a given local calendar day.
    Deletes existing sessions whose check_in falls on that local date, then rebuilds from logs.
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)

    start_local = datetime.combine(target, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    db.execute(
        delete(AttendanceSession).where(
            and_(
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        )
    )

    log_rows = db.execute(
        select(AttendanceLog).where(
            AttendanceLog.timestamp >= start_utc,
            AttendanceLog.timestamp < end_utc,
        )
    ).scalars().all()

    by_employee_day: dict[tuple[str, date], list[AttendanceLog]] = defaultdict(list)
    for lg in log_rows:
        d = _local_date(lg.timestamp, tz)
        if d == target:
            by_employee_day[(lg.employee_code, d)].append(lg)

    employees = db.execute(select(Employee)).scalars().all()
    code_to_employee: dict[str, Employee] = {str(e.device_user_id): e for e in employees}

    created = 0
    for (code, _day), day_logs in by_employee_day.items():
        emp = code_to_employee.get(code)
        if emp is None:
            continue
        pairs = _pair_logs_for_day(day_logs, tz)
        for cin_log, cout_log, status in pairs:
            check_in = cin_log.timestamp
            check_out = cout_log.timestamp if cout_log else None
            work_min: int | None = None
            if check_out and check_out > check_in:
                work_min = int((check_out - check_in).total_seconds() // 60)

            late = _minutes_late(check_in, emp.shift_start, tz)
            early = _minutes_early(check_out, emp.shift_end, tz) if check_out else None

            db.add(
                AttendanceSession(
                    employee_id=emp.id,
                    check_in=check_in,
                    check_out=check_out,
                    work_duration=work_min,
                    late_minutes=late,
                    early_minutes=early,
                    status=status,
                )
            )
            created += 1

    db.commit()
    return created


def run_device_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Fetch attendance from device, insert logs, rebuild sessions for today (local)."""
    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    records = device.fetch_attendance()
    n = insert_attendance_logs_idempotent(db, records, settings.zk_device_id)
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    rebuild_sessions_for_local_date(db, today, settings=settings)
    rebuild_sessions_for_local_date(db, today - timedelta(days=1), settings=settings)
    return len(records), n


def run_user_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Fetch users from device and insert new employees (ON CONFLICT DO NOTHING)."""
    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    users = device.fetch_users()
    inserted = sync_employees_from_device_users(db, users)
    return len(users), inserted
