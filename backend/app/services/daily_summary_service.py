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
from app.services.attendance_effective_service import effective_punches_for_summary
from app.services.punch_classification import classify_punch


def day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def compute_daily_summary(db: Session, summary_date: date, settings: Settings | None = None) -> list[DailySummaryRow]:
    cfg = settings or get_settings()
    start_utc, end_utc = day_bounds_utc(summary_date, cfg.timezone)

    employees = list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())
    effective_by_employee = effective_punches_for_summary(db, summary_date=summary_date, settings=cfg)

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
        emp_punches = effective_by_employee.get(emp.id, [])
        sess = sessions_by_employee_id.get(emp.id, [])

        first_in: datetime | None = None
        last_out: datetime | None = None
        if emp_punches:
            ins = [x.timestamp for x in emp_punches if classify_punch(x.punch_type) is True]
            first_in = min(ins) if ins else emp_punches[0].timestamp
            outs = [x.timestamp for x in emp_punches if classify_punch(x.punch_type) is False]
            if outs:
                last_out = max(outs)
            elif len(emp_punches) > 1:
                last_out = emp_punches[-1].timestamp

        if not emp_punches and not sess:
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

        total_min: int | None = None
        if first_in is not None and last_out is not None and last_out > first_in:
            total_min = int((last_out - first_in).total_seconds() // 60)
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

    rows.sort(key=lambda r: r.employee_name.lower())
    return rows
