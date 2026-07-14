"""Shared attendance utilities: local dates, pairing, mapping, session rebuild."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.device_user_mapping import DeviceUserMapping
from app.models.employee import Employee
from app.services.punch_classification import classify_punch, summarize_day_punches

_CHECK_IN_DIRECTION_CODES = ("0", "3", "4")
_ENROLLMENT_GAP_DAYS = 30


@dataclass(frozen=True)
class DayAttendanceSnapshot:
    """Day punches loaded from attendance_logs."""

    first_check_in: datetime | None
    last_check_out: datetime | None
    log_ids: list[int]
    log_timestamps: list[datetime]


def day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def resolve_mapping_for_punch(
    db: Session,
    *,
    device_id: str,
    device_user_id: str,
    at_time: datetime,
) -> DeviceUserMapping | None:
    return db.execute(
        select(DeviceUserMapping)
        .where(
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.device_user_id == device_user_id,
            DeviceUserMapping.valid_from <= at_time,
            or_(DeviceUserMapping.valid_to.is_(None), DeviceUserMapping.valid_to > at_time),
        )
        .order_by(DeviceUserMapping.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()


def pair_logs_for_day(
    logs: list[AttendanceLog],
    _tz: ZoneInfo,
    *,
    duplicate_window_seconds: int,
) -> list[tuple[AttendanceLog, AttendanceLog | None, str]]:
    """
    Pair IN/OUT for one employee for one local calendar day.
    Returns list of (check_in_log, check_out_log_or_none, status).
    """
    logs_sorted = sorted(logs, key=lambda x: x.timestamp)
    sessions: list[tuple[AttendanceLog, AttendanceLog | None, str]] = []
    pending_in: AttendanceLog | None = None
    next_expects_in = True
    duplicate_window = timedelta(seconds=duplicate_window_seconds)

    for log in logs_sorted:
        cls = classify_punch(log.punch_type)
        if cls is True:
            if pending_in is not None and duplicate_window.total_seconds() > 0:
                if log.timestamp - pending_in.timestamp <= duplicate_window:
                    continue
            if pending_in is not None:
                sessions.append((pending_in, None, "missing_check_out"))
            pending_in = log
            next_expects_in = False
        elif cls is False:
            if pending_in is None:
                continue
            if log.timestamp <= pending_in.timestamp:
                continue
            if duplicate_window.total_seconds() > 0 and log.timestamp - pending_in.timestamp <= duplicate_window:
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


def load_logs_for_employee_day(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> list[AttendanceLog]:
    settings = settings or get_settings()
    start_utc, end_utc = day_bounds_utc(local_date, settings.timezone)
    employee_code = str(employee.device_user_id)
    q = (
        select(AttendanceLog)
        .where(
            AttendanceLog.timestamp >= start_utc,
            AttendanceLog.timestamp < end_utc,
            AttendanceLog.employee_code == employee_code,
        )
        .order_by(AttendanceLog.timestamp)
    )
    if employee.employee_uuid:
        q = q.where(
            or_(
                AttendanceLog.employee_uuid == employee.employee_uuid,
                AttendanceLog.employee_uuid.is_(None),
            )
        )
    return list(db.execute(q).scalars().all())


def load_day_snapshot(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> DayAttendanceSnapshot:
    settings = settings or get_settings()
    logs = load_logs_for_employee_day(db, employee=employee, local_date=local_date, settings=settings)
    first_in, last_out, _ = summarize_day_punches(logs, tz_name=settings.timezone)
    return DayAttendanceSnapshot(
        first_check_in=first_in,
        last_check_out=last_out,
        log_ids=[log.id for log in logs],
        log_timestamps=[log.timestamp for log in logs],
    )


def summarize_employee_day_from_logs(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
    logs: list[AttendanceLog] | None = None,
) -> tuple[datetime | None, datetime | None, int | None, int]:
    settings = settings or get_settings()
    day_logs = logs if logs is not None else load_logs_for_employee_day(
        db, employee=employee, local_date=local_date, settings=settings
    )
    first_in, last_out, total_min = summarize_day_punches(day_logs, tz_name=settings.timezone)
    return first_in, last_out, total_min, len(day_logs)


def load_raw_punches_for_dates(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    employees: list[Employee],
    settings: Settings | None = None,
) -> dict[date, dict[int, list[AttendanceLog]]]:
    """Batch-load attendance_logs keyed by local date → employee_id."""
    settings = settings or get_settings()
    if not employees or end_date < start_date:
        return {}
    tz = ZoneInfo(settings.timezone)
    start_utc, _ = day_bounds_utc(start_date, settings.timezone)
    _, end_utc = day_bounds_utc(end_date, settings.timezone)
    code_to_emp = {str(e.device_user_id): e for e in employees if e.device_user_id}
    codes = list(code_to_emp.keys())
    if not codes:
        return {}
    rows = list(
        db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
                AttendanceLog.employee_code.in_(codes),
            )
            .order_by(AttendanceLog.timestamp)
        ).scalars().all()
    )
    out: dict[date, dict[int, list[AttendanceLog]]] = {}
    for log in rows:
        emp = code_to_emp.get(str(log.employee_code))
        if emp is None:
            continue
        day = local_date(log.timestamp, tz)
        out.setdefault(day, {}).setdefault(emp.id, []).append(log)
    return out


def _first_meaningful_check_in(
    check_ins: list[tuple[datetime, date, int]],
    all_timestamps: list[datetime],
) -> datetime | None:
    if not check_ins:
        return None
    gap = timedelta(days=_ENROLLMENT_GAP_DAYS)
    ordered_all = sorted(all_timestamps)

    def _next_punch_after(ts: datetime) -> datetime | None:
        for candidate in ordered_all:
            if candidate > ts:
                return candidate
        return None

    for ts, _local_date, day_count in check_ins:
        if day_count > 1:
            return ts
        next_ts = _next_punch_after(ts)
        if next_ts is None or next_ts - ts <= gap:
            return ts
    return check_ins[-1][0]


def employee_punch_bounds(
    db: Session,
    *,
    employee: Employee,
) -> tuple[datetime | None, datetime | None]:
    """Return (first_check_in, last_punch) from attendance_logs."""
    employee_code = str(employee.device_user_id)
    base_filters = (AttendanceLog.employee_code == employee_code,)
    mapping_filters: list = []
    if employee.employee_uuid:
        mapping_filters.append(
            exists(
                select(1)
                .select_from(DeviceUserMapping)
                .where(
                    DeviceUserMapping.employee_uuid == employee.employee_uuid,
                    DeviceUserMapping.valid_from <= AttendanceLog.timestamp,
                    or_(
                        DeviceUserMapping.valid_to.is_(None),
                        DeviceUserMapping.valid_to > AttendanceLog.timestamp,
                    ),
                )
            )
        )

    day_count = func.count().over(partition_by=func.date(AttendanceLog.timestamp)).label("day_count")
    check_in_rows = list(
        db.execute(
            select(AttendanceLog.timestamp, day_count)
            .where(
                *base_filters,
                AttendanceLog.punch_type.in_(_CHECK_IN_DIRECTION_CODES),
                *mapping_filters,
            )
            .order_by(AttendanceLog.timestamp)
        ).all()
    )
    all_ts = list(
        db.execute(
            select(AttendanceLog.timestamp)
            .where(*base_filters, *mapping_filters)
            .order_by(AttendanceLog.timestamp)
        ).scalars().all()
    )
    check_ins: list[tuple[datetime, date, int]] = [
        (ts, ts.date(), int(cnt)) for ts, cnt in check_in_rows
    ]
    first_in = _first_meaningful_check_in(check_ins, all_ts)
    last_punch = all_ts[-1] if all_ts else None
    return first_in, last_punch


def rebuild_sessions_for_employee_date(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
    settings: Settings | None = None,
    commit: bool = True,
) -> int:
    """Recompute sessions for one employee on one local date from attendance_logs."""
    settings = settings or get_settings()
    employee = db.get(Employee, employee_id)
    if employee is None:
        return 0
    tz = ZoneInfo(settings.timezone)
    start_utc, end_utc = day_bounds_utc(local_date, settings.timezone)

    db.execute(
        delete(AttendanceSession).where(
            and_(
                AttendanceSession.employee_id == employee_id,
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        )
    )

    logs = load_logs_for_employee_day(db, employee=employee, local_date=local_date, settings=settings)
    if not logs:
        if commit:
            db.commit()
        return 0

    pairs = pair_logs_for_day(
        logs,
        tz,
        duplicate_window_seconds=settings.duplicate_punch_window_seconds,
    )
    created = 0
    for cin_log, cout_log, status in pairs:
        check_in = cin_log.timestamp
        check_out = cout_log.timestamp if cout_log else None
        work_min: int | None = None
        if check_out and check_out > check_in:
            work_min = int((check_out - check_in).total_seconds() // 60)
        db.add(
            AttendanceSession(
                employee_id=employee_id,
                check_in=check_in,
                check_out=check_out,
                work_duration=work_min,
                status=status,
            )
        )
        created += 1
    if commit:
        db.commit()
    return created


def rebuild_sessions_for_local_date(
    db: Session,
    target: date,
    settings: Settings | None = None,
    *,
    commit: bool = True,
) -> int:
    """Rebuild sessions for all active employees on a date."""
    settings = settings or get_settings()
    employees = list(
        db.execute(select(Employee).where(Employee.departed_at.is_(None))).scalars().all()
    )
    total = 0
    for emp in employees:
        total += rebuild_sessions_for_employee_date(
            db, employee_id=emp.id, local_date=target, settings=settings, commit=False
        )
    if commit:
        db.commit()
    return total


def replace_employee_day_logs(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    device_id: str,
    settings: Settings | None = None,
) -> None:
    """Delete all logs for employee+day and insert the corrected IN/OUT punches."""
    settings = settings or get_settings()
    start_utc, end_utc = day_bounds_utc(local_date, settings.timezone)
    employee_code = str(employee.device_user_id)

    existing = list(
        db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_code == employee_code,
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
            )
        ).scalars().all()
    )
    for row in existing:
        db.delete(row)
    db.flush()

    mapping = resolve_mapping_for_punch(
        db,
        device_id=device_id,
        device_user_id=employee_code,
        at_time=new_check_in,
    )
    db.add(
        AttendanceLog(
            employee_code=employee_code,
            timestamp=new_check_in,
            device_id=device_id,
            employee_uuid=employee.employee_uuid,
            device_mapping_id=mapping.id if mapping else None,
            punch_type="0",
        )
    )
    if new_check_out is not None:
        mapping_out = resolve_mapping_for_punch(
            db,
            device_id=device_id,
            device_user_id=employee_code,
            at_time=new_check_out,
        )
        db.add(
            AttendanceLog(
                employee_code=employee_code,
                timestamp=new_check_out,
                device_id=device_id,
                employee_uuid=employee.employee_uuid,
                device_mapping_id=mapping_out.id if mapping_out else None,
                punch_type="1",
            )
        )
    db.flush()


def verify_imported_timestamps(
    *,
    expected_in: datetime | None,
    expected_out: datetime | None,
    imported_timestamps: list[datetime],
    tz_name: str,
) -> tuple[bool, bool]:
    from app.services.device_attlog_protocol import _ts_match

    has_in = expected_in is None or any(
        _ts_match(expected_in, ts, tz_name=tz_name) for ts in imported_timestamps
    )
    has_out = expected_out is None or any(
        _ts_match(expected_out, ts, tz_name=tz_name) for ts in imported_timestamps
    )
    return has_in, has_out
