"""GOD-mode attendance correction APIs."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_god_mode
from app.models.attendance_correction import AttendanceCorrection
from app.models.employee import Employee
from app.models.user import User
from app.services.attendance_correction_service import (
    apply_attendance_correction,
    load_day_snapshot,
)
from app.services.audit_service import append_audit_log
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported

router = APIRouter(prefix="/attendance/god", tags=["attendance-god"])


class GodDayPreview(BaseModel):
    employee_id: int
    local_date: date
    current_check_in: datetime | None
    current_check_out: datetime | None
    punch_count: int


class GodCorrectRequest(BaseModel):
    employee_id: int
    local_date: date
    new_check_in: datetime
    new_check_out: datetime | None = None


class GodCorrectionRead(BaseModel):
    correction_uuid: str
    employee_id: int
    local_date: date
    previous_check_in: datetime | None
    previous_check_out: datetime | None
    new_check_in: datetime | None
    new_check_out: datetime | None
    status: str
    device_command_uuid: str | None
    error_message: str | None
    applied_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("/day/{employee_id}", response_model=GodDayPreview)
def preview_god_day(
    employee_id: int,
    summary_date: date = Query(..., alias="date"),
    _god: User = Depends(require_god_mode),
    db: Session = Depends(get_db),
) -> GodDayPreview:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    snap = load_day_snapshot(db, employee=emp, local_date=summary_date)
    return GodDayPreview(
        employee_id=employee_id,
        local_date=summary_date,
        current_check_in=snap.first_check_in,
        current_check_out=snap.last_check_out,
        punch_count=len(snap.log_ids),
    )


@router.post("/correct", response_model=GodCorrectionRead)
def apply_god_correction(
    payload: GodCorrectRequest,
    request: Request,
    user: User = Depends(require_god_mode),
    db: Session = Depends(get_db),
) -> AttendanceCorrection:
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    check_in = payload.new_check_in if payload.new_check_in.tzinfo else payload.new_check_in.replace(tzinfo=tz)
    check_out = None
    if payload.new_check_out is not None:
        check_out = payload.new_check_out if payload.new_check_out.tzinfo else payload.new_check_out.replace(tzinfo=tz)

    try:
        correction = apply_attendance_correction(
            db,
            employee_id=payload.employee_id,
            local_date=payload.local_date,
            new_check_in=check_in.astimezone(ZoneInfo("UTC")),
            new_check_out=check_out.astimezone(ZoneInfo("UTC")) if check_out else None,
            actor_user_uuid=user.user_uuid,
            correlation_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AttlogCorrectionNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except AttlogCorrectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    append_audit_log(
        db,
        actor_user_uuid=user.user_uuid,
        action_type="GOD_ATTENDANCE_CORRECT",
        entity_type="attendance_correction",
        entity_id=correction.correction_uuid,
        previous_state={
            "check_in": correction.previous_check_in.isoformat() if correction.previous_check_in else None,
            "check_out": correction.previous_check_out.isoformat() if correction.previous_check_out else None,
        },
        new_state={
            "check_in": correction.new_check_in.isoformat() if correction.new_check_in else None,
            "check_out": correction.new_check_out.isoformat() if correction.new_check_out else None,
            "local_date": correction.local_date.isoformat(),
            "employee_id": correction.employee_id,
        },
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    db.refresh(correction)
    return correction


@router.get("/corrections", response_model=list[GodCorrectionRead])
def list_god_corrections(
    limit: int = Query(50, ge=1, le=200),
    _god: User = Depends(require_god_mode),
    db: Session = Depends(get_db),
) -> list[AttendanceCorrection]:
    rows = list(
        db.execute(
            select(AttendanceCorrection).order_by(AttendanceCorrection.created_at.desc()).limit(limit)
        ).scalars().all()
    )
    return rows
