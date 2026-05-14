"""Attendance logs, sessions, and summaries."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
from app.schemas.attendance import AttendanceLogRead, AttendanceSessionRead, DailySummaryRow
from app.services.daily_summary_service import compute_daily_summary, day_bounds_utc

router = APIRouter(
    prefix="/attendance",
    tags=["attendance"],
    dependencies=[Depends(require_permissions(Permission.REPORT_READ))],
)


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
        start, _ = day_bounds_utc(date_from, tz)
        q = q.where(AttendanceLog.timestamp >= start)
    if date_to is not None:
        _, end = day_bounds_utc(date_to, tz)
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
        start, _ = day_bounds_utc(date_from, tz)
        q = q.where(AttendanceSession.check_in >= start)
    if date_to is not None:
        _, end = day_bounds_utc(date_to, tz)
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
    return compute_daily_summary(db, summary_date, settings)


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
        start, _ = day_bounds_utc(date_from, tz)
        q = q.where(AttendanceSession.check_in >= start)
    if date_to is not None:
        _, end = day_bounds_utc(date_to, tz)
        q = q.where(AttendanceSession.check_in < end)
    q = q.order_by(AttendanceSession.check_in.desc())
    return list(db.execute(q).scalars().all())
