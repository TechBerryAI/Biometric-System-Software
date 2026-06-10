"""Daily per-employee attendance summary (local calendar day in configured TIMEZONE)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import DailySummaryRow
from app.services.punch_classification import classify_punch


def day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def compute_daily_summary(db: Session, summary_date: date, settings: Settings | None = None) -> list[DailySummaryRow]:
    cfg = settings or get_settings()
    tz_name = cfg.timezone
    start_utc, end_utc = day_bounds_utc(summary_date, tz_name)

    employees = list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())
    logs = list(
        db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
            )
            .order_by(AttendanceLog.timestamp)
        ).scalars()
    )
    by_employee_uuid: dict[str, list[AttendanceLog]] = {}
    by_code: dict[str, list[AttendanceLog]] = {}
    for lg in logs:
        if lg.employee_uuid:
            by_employee_uuid.setdefault(lg.employee_uuid, []).append(lg)
        by_code.setdefault(lg.employee_code, []).append(lg)

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
        if emp.employee_uuid and emp.employee_uuid in by_employee_uuid:
            emp_logs = by_employee_uuid[emp.employee_uuid]
        else:
            emp_logs = by_code.get(str(emp.device_user_id), [])
        sess = sessions_by_employee_id.get(emp.id, [])

        first_in: datetime | None = None
        last_out: datetime | None = None
        if emp_logs:
            ins = [x.timestamp for x in emp_logs if classify_punch(x.punch_type) is True]
            first_in = min(ins) if ins else emp_logs[0].timestamp
            outs = [x.timestamp for x in emp_logs if classify_punch(x.punch_type) is False]
            if outs:
                last_out = max(outs)
            elif len(emp_logs) > 1:
                last_out = emp_logs[-1].timestamp
            else:
                last_out = None

        if not emp_logs and not sess:
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
