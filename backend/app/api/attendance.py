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
from app.services.attendance_helpers import day_bounds_utc
from app.services.daily_summary_service import compute_daily_summary, compute_daily_summaries_range

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
    employee_id: int | None = Query(None, description="Filter by internal employee id"),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> list[AttendanceLogRead]:
    """Attendance punches from attendance_logs (single source of truth)."""
    settings = get_settings()
    tz = settings.timezone
    max_limit = settings.attendance_api_max_limit
    applied_limit = min(limit if limit is not None else settings.attendance_api_default_limit, max_limit)
    q = select(AttendanceLog).order_by(AttendanceLog.timestamp.desc()).offset(offset).limit(applied_limit)
    if date_from is not None:
        start, _ = day_bounds_utc(date_from, tz)
        q = q.where(AttendanceLog.timestamp >= start)
    if date_to is not None:
        _, end = day_bounds_utc(date_to, tz)
        q = q.where(AttendanceLog.timestamp < end)
    if employee_code is not None:
        q = q.where(AttendanceLog.employee_code == employee_code)
    if employee_id is not None:
        emp = db.get(Employee, employee_id)
        if emp is None:
            return []
        q = q.where(AttendanceLog.employee_code == str(emp.device_user_id))
    rows = list(db.execute(q).scalars().all())
    return [
        AttendanceLogRead(
            id=log.id,
            employee_code=log.employee_code,
            timestamp=log.timestamp,
            device_id=log.device_id,
            punch_type=log.punch_type,
            created_at=log.created_at,
        )
        for log in rows
    ]


@router.get("/sessions", response_model=list[AttendanceSessionRead])
def list_attendance_sessions(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    employee_id: int | None = Query(None, description="Filter by internal employee id"),
    limit: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> list[AttendanceSession]:
    settings = get_settings()
    tz = settings.timezone
    max_limit = settings.attendance_api_max_limit
    applied_limit = min(limit if limit is not None else settings.attendance_api_default_limit, max_limit)
    q = select(AttendanceSession).order_by(AttendanceSession.check_in.desc()).limit(applied_limit)
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


@router.get("/daily-summary/range", response_model=dict[str, list[DailySummaryRow]])
def daily_summary_range(
    date_from: date = Query(..., alias="from", description="Start local date (inclusive)"),
    date_to: date = Query(..., alias="to", description="End local date (inclusive)"),
    db: Session = Depends(get_db),
) -> dict[str, list[DailySummaryRow]]:
    settings = get_settings()
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'to' date must be on or after 'from' date",
        )
    span = (date_to - date_from).days + 1
    if span > 93:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 93 days",
        )
    summaries = compute_daily_summaries_range(db, date_from, date_to, settings)
    return {d.isoformat(): rows for d, rows in summaries.items()}


@router.get("/{employee_id}", response_model=list[AttendanceSessionRead])
def list_employee_attendance(
    employee_id: int,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    limit: int | None = Query(None, ge=1),
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
    max_limit = settings.attendance_api_max_limit
    applied_limit = min(limit if limit is not None else settings.attendance_api_default_limit, max_limit)
    q = q.order_by(AttendanceSession.check_in.desc()).limit(applied_limit)
    return list(db.execute(q).scalars().all())
