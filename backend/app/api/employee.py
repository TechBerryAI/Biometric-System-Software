"""Employee HTTP routes."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi import HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDailyAttendanceRead,
    EmployeeDetailRead,
    EmployeeRead,
)

router = APIRouter(prefix="/employees", tags=["employees"])


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


@router.get("", response_model=list[EmployeeRead])
def list_employees(db: Session = Depends(get_db)) -> list[Employee]:
    return list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())


@router.get("/{employee_id}", response_model=EmployeeDetailRead)
def get_employee(employee_id: int, db: Session = Depends(get_db)) -> EmployeeDetailRead:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    total_logs = (
        db.execute(
            select(func.count())
            .select_from(AttendanceLog)
            .where(AttendanceLog.employee_code == emp.device_user_id)
        ).scalar_one()
        or 0
    )
    first_punch_at, last_punch_at = db.execute(
        select(func.min(AttendanceLog.timestamp), func.max(AttendanceLog.timestamp)).where(
            AttendanceLog.employee_code == emp.device_user_id
        )
    ).one()
    log_rows = list(
        db.execute(
            select(AttendanceLog.timestamp, AttendanceLog.punch_type)
            .where(AttendanceLog.employee_code == emp.device_user_id)
            .order_by(AttendanceLog.timestamp)
        )
    )
    tz = ZoneInfo(get_settings().timezone)
    days: dict[date, list[str]] = {}
    for ts, punch_type in log_rows:
        d = ts.astimezone(tz).date()
        days.setdefault(d, []).append(str(punch_type))
    total_attendance_days = len(days)
    total_complete_days = sum(1 for punches in days.values() if len(punches) > 1)

    return EmployeeDetailRead(
        id=emp.id,
        device_user_id=emp.device_user_id,
        device_uid=emp.device_uid,
        device_privilege=emp.device_privilege,
        device_group_id=emp.device_group_id,
        device_card=emp.device_card,
        name=emp.name,
        department=emp.department,
        shift_start=emp.shift_start,
        shift_end=emp.shift_end,
        created_at=emp.created_at,
        total_logs=total_logs,
        first_punch_at=first_punch_at,
        last_punch_at=last_punch_at,
        total_attendance_days=total_attendance_days,
        total_complete_days=total_complete_days,
    )


@router.get("/{employee_id}/daily-attendance", response_model=list[EmployeeDailyAttendanceRead])
def get_employee_daily_attendance(
    employee_id: int,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[EmployeeDailyAttendanceRead]:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    local_today = datetime.now(tz).date()
    start_date = date_from or (local_today - timedelta(days=30))
    end_date = date_to or local_today
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'to' date must be on or after 'from' date",
        )

    start_utc, _ = _day_bounds_utc(start_date, settings.timezone)
    _, end_utc = _day_bounds_utc(end_date, settings.timezone)
    end_utc = end_utc

    logs = list(
        db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.employee_code == emp.device_user_id,
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
            )
            .order_by(AttendanceLog.timestamp)
        ).scalars()
    )

    by_day: dict[date, list[AttendanceLog]] = {}
    for lg in logs:
        local_day = lg.timestamp.astimezone(tz).date()
        by_day.setdefault(local_day, []).append(lg)

    rows: list[EmployeeDailyAttendanceRead] = []
    d = start_date
    while d <= end_date:
        day_logs = by_day.get(d, [])
        if not day_logs:
            rows.append(
                EmployeeDailyAttendanceRead(
                    summary_date=d,
                    first_check_in=None,
                    last_check_out=None,
                    total_work_minutes=None,
                    late_arrival=False,
                    absent=True,
                    punch_count=0,
                )
            )
            d += timedelta(days=1)
            continue

        ins = [x.timestamp for x in day_logs if _is_in_punch(x.punch_type) is True]
        first_in = min(ins) if ins else day_logs[0].timestamp
        outs = [x.timestamp for x in day_logs if _is_in_punch(x.punch_type) is False]
        if outs:
            last_out = max(outs)
        elif len(day_logs) > 1:
            last_out = day_logs[-1].timestamp
        else:
            last_out = None

        total_work_minutes: int | None = None
        if first_in is not None and last_out is not None and last_out > first_in:
            total_work_minutes = int((last_out - first_in).total_seconds() // 60)

        if first_in is not None:
            local_in = first_in.astimezone(tz)
            shift_start = emp.shift_start or settings.default_shift_start
            shift_dt = datetime.combine(local_in.date(), shift_start, tzinfo=tz)
            late_arrival = local_in > shift_dt
        else:
            late_arrival = False

        rows.append(
            EmployeeDailyAttendanceRead(
                summary_date=d,
                first_check_in=first_in,
                last_check_out=last_out,
                total_work_minutes=total_work_minutes,
                late_arrival=late_arrival,
                absent=False,
                punch_count=len(day_logs),
            )
        )
        d += timedelta(days=1)

    rows.sort(key=lambda r: r.summary_date, reverse=True)
    return rows


@router.post("", response_model=EmployeeRead)
def upsert_employee_metadata(payload: EmployeeCreate, db: Session = Depends(get_db)) -> Employee:
    """
    Create or update employee metadata in DB only (does not push to device).
    device_user_id must match the terminal user id.
    """
    existing = db.execute(
        select(Employee).where(Employee.device_user_id == payload.device_user_id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.name = payload.name
        existing.department = payload.department
        existing.shift_start = payload.shift_start
        existing.shift_end = payload.shift_end
        db.commit()
        db.refresh(existing)
        return existing
    emp = Employee(
        device_user_id=payload.device_user_id,
        name=payload.name,
        department=payload.department,
        shift_start=payload.shift_start,
        shift_end=payload.shift_end,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp
