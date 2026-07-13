"""Daily per-employee attendance summary from raw device punches (read-only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import DailySummaryRow
from app.services.attendance_effective_service import (
    load_raw_punches_for_dates,
    summarize_employee_day_from_events,
)


def day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def _daily_summary_sort_key(row: DailySummaryRow) -> tuple:
    """Present employees first by check-in time; partial/out-only next; absent last."""
    if row.first_check_in is not None:
        return (0, row.first_check_in, row.employee_name.lower())
    if row.last_check_out is not None:
        return (1, row.last_check_out, row.employee_name.lower())
    absent_marker = datetime.min.replace(tzinfo=ZoneInfo("UTC"))
    return (2, absent_marker, row.employee_name.lower())


def _load_sessions_for_dates(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    tz_name: str,
) -> dict[date, dict[int, list[AttendanceSession]]]:
    start_utc, _ = day_bounds_utc(start_date, tz_name)
    _, end_utc = day_bounds_utc(end_date, tz_name)
    sessions = list(
        db.execute(
            select(AttendanceSession).where(
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        ).scalars().all()
    )
    tz = ZoneInfo(tz_name)
    grouped: dict[date, dict[int, list[AttendanceSession]]] = defaultdict(lambda: defaultdict(list))
    for sess in sessions:
        local_day = sess.check_in.astimezone(tz).date()
        grouped[local_day][sess.employee_id].append(sess)
    return grouped


def compute_daily_summaries_range(
    db: Session,
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> dict[date, list[DailySummaryRow]]:
    """Read-only batch summary from full raw punches (events + logs)."""
    if end_date < start_date:
        return {}
    cfg = settings or get_settings()
    employees = list(
        db.execute(
            select(Employee).where(Employee.departed_at.is_(None)).order_by(Employee.id)
        ).scalars().all()
    )
    raw_by_day = load_raw_punches_for_dates(
        db, start_date=start_date, end_date=end_date, employees=employees, settings=cfg
    )
    sessions = _load_sessions_for_dates(db, start_date=start_date, end_date=end_date, tz_name=cfg.timezone)

    out: dict[date, list[DailySummaryRow]] = {}
    d = start_date
    while d <= end_date:
        day_raw = raw_by_day.get(d, {})
        day_sessions = sessions.get(d, {})
        rows: list[DailySummaryRow] = []
        for emp in employees:
            first_in, last_out, total_min, punch_count = summarize_employee_day_from_events(
                db,
                employee=emp,
                local_date=d,
                settings=cfg,
                raw_punches=day_raw.get(emp.id),
            )
            sess_count = len(day_sessions.get(emp.id, []))
            rows.append(
                DailySummaryRow(
                    summary_date=d,
                    employee_id=emp.id,
                    device_user_id=emp.device_user_id,
                    employee_name=emp.name,
                    first_check_in=first_in,
                    last_check_out=last_out,
                    total_work_minutes=total_min,
                    sessions_count=sess_count if punch_count > 0 else 0,
                )
            )
        rows.sort(key=_daily_summary_sort_key)
        out[d] = rows
        d += timedelta(days=1)
    return out


def compute_daily_summary(db: Session, summary_date: date, settings: Settings | None = None) -> list[DailySummaryRow]:
    """Read-only summary for one local date."""
    cfg = settings or get_settings()
    return compute_daily_summaries_range(db, summary_date, summary_date, settings=cfg).get(summary_date, [])
