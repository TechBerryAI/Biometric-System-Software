"""Daily per-employee attendance summary from effective punches (read-only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_effective_punch import AttendanceEffectivePunch
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import DailySummaryRow
from app.services.attendance_effective_service import (
    summarize_day_punches,
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


def _row_from_punches(
    *,
    summary_date: date,
    emp: Employee,
    punches: list[AttendanceEffectivePunch],
    sessions_count: int,
    tz_name: str,
) -> DailySummaryRow:
    if not punches:
        if sessions_count == 0:
            return DailySummaryRow(
                summary_date=summary_date,
                employee_id=emp.id,
                device_user_id=emp.device_user_id,
                employee_name=emp.name,
                first_check_in=None,
                last_check_out=None,
                total_work_minutes=None,
                sessions_count=0,
            )
        first_in, last_out, total_min = None, None, None
    else:
        first_in, last_out, total_min = summarize_day_punches(punches, tz_name=tz_name)
    return DailySummaryRow(
        summary_date=summary_date,
        employee_id=emp.id,
        device_user_id=emp.device_user_id,
        employee_name=emp.name,
        first_check_in=first_in,
        last_check_out=last_out,
        total_work_minutes=total_min,
        sessions_count=sessions_count,
    )


def _load_effective_punches_for_dates(
    db: Session,
    *,
    start_date: date,
    end_date: date,
) -> dict[date, dict[int, list[AttendanceEffectivePunch]]]:
    rows = list(
        db.execute(
            select(AttendanceEffectivePunch).where(
                AttendanceEffectivePunch.local_date >= start_date,
                AttendanceEffectivePunch.local_date <= end_date,
                AttendanceEffectivePunch.is_active.is_(True),
            )
        ).scalars().all()
    )
    grouped: dict[date, dict[int, list[AttendanceEffectivePunch]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row.local_date][row.employee_id].append(row)
    for day_map in grouped.values():
        for emp_id in day_map:
            day_map[emp_id].sort(key=lambda p: p.timestamp)
    return grouped


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
    """Read-only batch summary for a date range (no rebuilds)."""
    if end_date < start_date:
        return {}
    cfg = settings or get_settings()
    employees = list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())
    effective = _load_effective_punches_for_dates(db, start_date=start_date, end_date=end_date)
    sessions = _load_sessions_for_dates(db, start_date=start_date, end_date=end_date, tz_name=cfg.timezone)

    out: dict[date, list[DailySummaryRow]] = {}
    d = start_date
    while d <= end_date:
        day_effective = effective.get(d, {})
        day_sessions = sessions.get(d, {})
        rows: list[DailySummaryRow] = []
        for emp in employees:
            punches = day_effective.get(emp.id, [])
            sess_count = len(day_sessions.get(emp.id, []))
            if punches:
                rows.append(
                    _row_from_punches(
                        summary_date=d,
                        emp=emp,
                        punches=punches,
                        sessions_count=sess_count,
                        tz_name=cfg.timezone,
                    )
                )
            elif sess_count == 0:
                rows.append(
                    DailySummaryRow(
                        summary_date=d,
                        employee_id=emp.id,
                        device_user_id=emp.device_user_id,
                        employee_name=emp.name,
                        first_check_in=None,
                        last_check_out=None,
                        total_work_minutes=None,
                        sessions_count=0,
                    )
                )
            else:
                first_in, last_out, total_min, punch_count = summarize_employee_day_from_events(
                    db, employee=emp, local_date=d, settings=cfg
                )
                if punch_count == 0:
                    rows.append(
                        DailySummaryRow(
                            summary_date=d,
                            employee_id=emp.id,
                            device_user_id=emp.device_user_id,
                            employee_name=emp.name,
                            first_check_in=None,
                            last_check_out=None,
                            total_work_minutes=None,
                            sessions_count=sess_count,
                        )
                    )
                else:
                    rows.append(
                        DailySummaryRow(
                            summary_date=d,
                            employee_id=emp.id,
                            device_user_id=emp.device_user_id,
                            employee_name=emp.name,
                            first_check_in=first_in,
                            last_check_out=last_out,
                            total_work_minutes=total_min,
                            sessions_count=sess_count,
                        )
                    )
        rows.sort(key=_daily_summary_sort_key)
        out[d] = rows
        d += timedelta(days=1)
    return out


def compute_daily_summary(db: Session, summary_date: date, settings: Settings | None = None) -> list[DailySummaryRow]:
    """Read-only summary for one local date (no rebuilds)."""
    cfg = settings or get_settings()
    return compute_daily_summaries_range(db, summary_date, summary_date, settings=cfg).get(summary_date, [])
