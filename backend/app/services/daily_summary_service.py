"""Daily per-employee attendance summary from effective punches."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import DailySummaryRow
from app.services.attendance_effective_service import (
    rebuild_sessions_for_employee_date,
    summarize_employee_day_from_events,
    ensure_effective_punches_for_day,
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


def compute_daily_summary(db: Session, summary_date: date, settings: Settings | None = None) -> list[DailySummaryRow]:
    cfg = settings or get_settings()
    start_utc, end_utc = day_bounds_utc(summary_date, cfg.timezone)

    employees = list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())
    for emp in employees:
        ensure_effective_punches_for_day(db, employee=emp, local_date=summary_date, settings=cfg, commit=False)
    db.commit()

    sessions = list(
        db.execute(
            select(AttendanceSession).where(
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        ).scalars()
    )
    sessions_by_employee_id: dict[int, list[AttendanceSession]] = {}
    for sess in sessions:
        sessions_by_employee_id.setdefault(sess.employee_id, []).append(sess)

    rows: list[DailySummaryRow] = []
    for emp in employees:
        first_in, last_out, total_min, punch_count = summarize_employee_day_from_events(
            db, employee=emp, local_date=summary_date, settings=cfg
        )
        sess = sessions_by_employee_id.get(emp.id, [])

        if punch_count == 0 and not sess:
            rows.append(
                DailySummaryRow(
                    summary_date=summary_date,
                    employee_id=emp.id,
                    device_user_id=emp.device_user_id,
                    employee_name=emp.name,
                    first_check_in=None,
                    last_check_out=None,
                    total_work_minutes=None,
                    sessions_count=0,
                )
            )
            continue

        rows.append(
            DailySummaryRow(
                summary_date=summary_date,
                employee_id=emp.id,
                device_user_id=emp.device_user_id,
                employee_name=emp.name,
                first_check_in=first_in,
                last_check_out=last_out,
                total_work_minutes=total_min,
                sessions_count=len(sess),
            )
        )

    rows.sort(key=_daily_summary_sort_key)
    return rows
