"""Internal attendance adjustment APIs — device-first, no correction ledger."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_operator_account
from app.domains.employees.models.employee import Employee
from app.domains.auth.models.user import User
from app.domains.attendance.services.attendance_correction_service import (
    CORRECTION_STATUS_DEVICE_PENDING,
    AttendanceAdjustmentResult,
    apply_attendance_correction,
    get_adjustment_command_status,
    probe_correction_capabilities,
)
from app.domains.attendance.services.attendance_helpers import load_day_snapshot
from app.shared.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported, DeviceLockContentionError

router = APIRouter(prefix="/attendance/adjust", tags=["attendance-adjust"])


class DayAdjustmentPreview(BaseModel):
    employee_id: int
    local_date: date
    current_check_in: datetime | None
    current_check_out: datetime | None
    punch_count: int


class AttendanceAdjustRequest(BaseModel):
    employee_id: int
    local_date: date
    new_check_in: datetime | None = None
    new_check_out: datetime | None = None


class AttendanceAdjustmentRead(BaseModel):
    employee_id: int
    local_date: date
    previous_check_in: datetime | None
    previous_check_out: datetime | None
    new_check_in: datetime | None
    new_check_out: datetime | None
    status: str
    device_updated: bool = False
    device_command_uuid: str | None
    device_tier: str | None = None
    error_message: str | None
    applied_at: datetime | None


class CorrectionCapabilitiesRead(BaseModel):
    tier: str
    record_size: int | None = None
    supports_selective_delete: bool = False
    supports_full_rewrite: bool = False
    supports_write: bool = False
    strict_device_authority: bool = True
    correction_allow_db_only_fallback: bool = False


def _adjustment_read(result: AttendanceAdjustmentResult) -> AttendanceAdjustmentRead:
    return AttendanceAdjustmentRead(
        employee_id=result.employee_id,
        local_date=result.local_date,
        previous_check_in=result.previous_check_in,
        previous_check_out=result.previous_check_out,
        new_check_in=result.new_check_in,
        new_check_out=result.new_check_out,
        status=result.status,
        device_updated=result.device_updated,
        device_command_uuid=result.device_command_uuid,
        device_tier=result.device_tier,
        error_message=result.error_message,
        applied_at=result.applied_at,
    )


@router.get("/capabilities", response_model=CorrectionCapabilitiesRead)
def get_correction_capabilities(
    _operator: User = Depends(require_operator_account),
    db: Session = Depends(get_db),
) -> CorrectionCapabilitiesRead:
    caps = probe_correction_capabilities(db=db)
    writable = bool(caps.get("supports_write"))
    return CorrectionCapabilitiesRead(
        tier=str(caps.get("tier") or "C"),
        record_size=int(caps["record_size"]) if caps.get("record_size") is not None else None,
        supports_selective_delete=bool(caps.get("supports_selective_delete")),
        supports_full_rewrite=bool(caps.get("supports_full_rewrite")),
        supports_write=writable,
        strict_device_authority=writable,
        correction_allow_db_only_fallback=not writable,
    )


@router.get("/commands/{command_uuid}", response_model=AttendanceAdjustmentRead)
def get_correction_command_status(
    command_uuid: str,
    _operator: User = Depends(require_operator_account),
    db: Session = Depends(get_db),
) -> AttendanceAdjustmentRead:
    result = get_adjustment_command_status(db, command_uuid=command_uuid)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    return _adjustment_read(result)


@router.get("/day/{employee_id}", response_model=DayAdjustmentPreview)
def preview_adjustment_day(
    employee_id: int,
    summary_date: date = Query(..., alias="date"),
    _operator: User = Depends(require_operator_account),
    db: Session = Depends(get_db),
) -> DayAdjustmentPreview:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    snap = load_day_snapshot(db, employee=emp, local_date=summary_date)
    return DayAdjustmentPreview(
        employee_id=employee_id,
        local_date=summary_date,
        current_check_in=snap.first_check_in,
        current_check_out=snap.last_check_out,
        punch_count=len(snap.log_ids),
    )


@router.post(
    "/correct",
    response_model=AttendanceAdjustmentRead,
    responses={202: {"description": "Device operation queued (device_pending)."}},
)
def apply_attendance_adjustment(
    payload: AttendanceAdjustRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_operator_account),
    db: Session = Depends(get_db),
) -> AttendanceAdjustmentRead:
    settings = get_settings()
    tz = ZoneInfo(settings.resolved_timezone())
    check_in = None
    if payload.new_check_in is not None:
        check_in = (
            payload.new_check_in
            if payload.new_check_in.tzinfo
            else payload.new_check_in.replace(tzinfo=tz)
        )
    check_out = None
    if payload.new_check_out is not None:
        check_out = (
            payload.new_check_out
            if payload.new_check_out.tzinfo
            else payload.new_check_out.replace(tzinfo=tz)
        )

    try:
        result = apply_attendance_correction(
            db,
            employee_id=payload.employee_id,
            local_date=payload.local_date,
            new_check_in=check_in.astimezone(ZoneInfo("UTC")) if check_in else None,
            new_check_out=check_out.astimezone(ZoneInfo("UTC")) if check_out else None,
            actor_user_uuid=user.user_uuid,
            correlation_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DeviceLockContentionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AttlogCorrectionNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except AttlogCorrectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if result.status == CORRECTION_STATUS_DEVICE_PENDING:
        response.status_code = status.HTTP_202_ACCEPTED

    return _adjustment_read(result)
