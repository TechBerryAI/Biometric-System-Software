"""Attendance logs, sessions, and summaries."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import AttendanceLogRead, AttendanceSessionRead, DailySummaryRow

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def _is_in_punch(punch_type: str) -> bool | None:
    p = punch_type.strip().lower()
    if p in ("0", "in", "check_in", "i"):
        return True
    if p in ("1", "out", "check_out", "o"):
        return False
    return None


@router.get("/logs", response_model=list[AttendanceLogRead])
def list_attendance_logs(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    employee_code: str | None = None,
    db: Session = Depends(get_db),
) -> list[AttendanceLog]:
    settings = get_settings()
    tz = settings.timezone
    q = select(AttendanceLog).order_by(AttendanceLog.timestamp.desc())
    if date_from is not None:
        start, _ = _day_bounds_utc(date_from, tz)
        q = q.where(AttendanceLog.timestamp >= start)
    if date_to is not None:
        _, end = _day_bounds_utc(date_to, tz)
        q = q.where(AttendanceLog.timestamp < end)
    if employee_code is not None:
        q = q.where(AttendanceLog.employee_code == employee_code)
    return list(db.execute(q).scalars().all())


@router.get("/sessions", response_model=list[AttendanceSessionRead])
def list_attendance_sessions(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    employee_id: int | None = Query(None, description="Filter by internal employee id"),
    db: Session = Depends(get_db),
) -> list[AttendanceSession]:
    settings = get_settings()
    tz = settings.timezone
    q = select(AttendanceSession).order_by(AttendanceSession.check_in.desc())
    if date_from is not None:
        start, _ = _day_bounds_utc(date_from, tz)
        q = q.where(AttendanceSession.check_in >= start)
    if date_to is not None:
        _, end = _day_bounds_utc(date_to, tz)
        q = q.where(AttendanceSession.check_in < end)
    if employee_id is not None:
        q = q.where(AttendanceSession.employee_id == employee_id)
    return list(db.execute(q).scalars().all())


@router.get("/daily-summary", response_model=list[DailySummaryRow])
def daily_summary(
    summary_date: date | None = Query(None, description="Local date; defaults to today in TIMEZONE"),
    db: Session = Depends(get_db),
) -> list[DailySummaryRow]:
    settings = get_settings()
    tz_name = settings.timezone
    if summary_date is None:
        summary_date = datetime.now(ZoneInfo(tz_name)).date()
    start_utc, end_utc = _day_bounds_utc(summary_date, tz_name)

    employees = list(db.execute(select(Employee)).scalars().all())
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
    by_code: dict[str, list[AttendanceLog]] = {}
    for lg in logs:
        by_code.setdefault(lg.employee_code, []).append(lg)

    rows: list[DailySummaryRow] = []
    tz = ZoneInfo(tz_name)

    for emp in employees:
        emp_logs = by_code.get(str(emp.device_user_id), [])
        sess = db.execute(
            select(AttendanceSession)
            .where(
                AttendanceSession.employee_id == emp.id,
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
            .order_by(AttendanceSession.check_in)
        ).scalars().all()

        # Prefer raw logs for visibility (shows anyone who punched),
        # even if session pairing is incomplete for the day.
        first_in: datetime | None = None
        last_out: datetime | None = None
        if emp_logs:
            # earliest known IN punch, fallback to earliest punch if type unknown
            ins = [x.timestamp for x in emp_logs if _is_in_punch(x.punch_type) is True]
            first_in = min(ins) if ins else emp_logs[0].timestamp
            outs = [x.timestamp for x in emp_logs if _is_in_punch(x.punch_type) is False]
            if outs:
                last_out = max(outs)
            elif len(emp_logs) > 1:
                # Some devices send only punch=0; use day's last punch as effective checkout.
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
                    late_arrival=False,
                    sessions_count=0,
                )
            )
            continue

        total_min: int | None = None
        if first_in is not None and last_out is not None and last_out > first_in:
            total_min = int((last_out - first_in).total_seconds() // 60)
        if first_in is not None and emp.shift_start is not None:
            local_in = first_in.astimezone(tz)
            shift_dt = datetime.combine(local_in.date(), emp.shift_start, tzinfo=tz)
            late_any = local_in > shift_dt
        elif first_in is not None:
            local_in = first_in.astimezone(tz)
            shift_dt = datetime.combine(local_in.date(), settings.default_shift_start, tzinfo=tz)
            late_any = local_in > shift_dt
        else:
            late_any = any((s.late_minutes or 0) > 0 for s in sess)

        rows.append(
            DailySummaryRow(
                summary_date=summary_date,
                employee_id=emp.id,
                device_user_id=emp.device_user_id,
                employee_name=emp.name,
                first_check_in=first_in,
                last_check_out=last_out,
                total_work_minutes=total_min,
                late_arrival=late_any,
                sessions_count=len(emp_logs),
            )
        )

    rows.sort(key=lambda r: r.employee_name.lower())
    return rows


@router.get("/{employee_id}", response_model=list[AttendanceSessionRead])
def list_employee_attendance(
    employee_id: int,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[AttendanceSession]:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    settings = get_settings()
    tz = settings.timezone
    q = select(AttendanceSession).where(AttendanceSession.employee_id == employee_id)
    if date_from is not None:
        start, _ = _day_bounds_utc(date_from, tz)
        q = q.where(AttendanceSession.check_in >= start)
    if date_to is not None:
        _, end = _day_bounds_utc(date_to, tz)
        q = q.where(AttendanceSession.check_in < end)
    q = q.order_by(AttendanceSession.check_in.desc())
    return list(db.execute(q).scalars().all())
