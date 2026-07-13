"""Privileged attendance adjustment APIs (reserved account only)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_privileged_account
from app.models.attendance_correction import AttendanceCorrection
from app.models.employee import Employee
from app.models.user import User
from app.services.attendance_correction_service import (
    CORRECTION_STATUS_APPLIED,
    CORRECTION_STATUS_DEVICE_PENDING,
    apply_attendance_correction,
    load_day_snapshot,
    probe_correction_capabilities,
)
from app.services.audit_service import append_audit_log
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported, DeviceLockContentionError
from app.services.device_service import DeviceService

router = APIRouter(prefix="/attendance/adjust", tags=["attendance-adjust"])

AUDIT_ACTION_ATTENDANCE_ADJUST = "ATTENDANCE_ADJUST"


class DayAdjustmentPreview(BaseModel):
    employee_id: int
    local_date: date
    current_check_in: datetime | None
    current_check_out: datetime | None
    punch_count: int


class AttendanceAdjustRequest(BaseModel):
    employee_id: int
    local_date: date
    new_check_in: datetime
    new_check_out: datetime | None = None


class AttendanceAdjustmentRead(BaseModel):
    correction_uuid: str
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
    correction_mode: str | None = None
    reimport_completed_at: datetime | None = None
    error_message: str | None
    applied_at: datetime | None

    model_config = {"from_attributes": True}


class CorrectionCapabilitiesRead(BaseModel):
    tier: str
    record_size: int | None = None
    supports_selective_delete: bool = False
    supports_full_rewrite: bool = False
    supports_write: bool = False
    strict_device_authority: bool = False
    correction_allow_db_only_fallback: bool = True


def _adjustment_read(correction: AttendanceCorrection) -> AttendanceAdjustmentRead:
    return AttendanceAdjustmentRead(
        correction_uuid=correction.correction_uuid,
        employee_id=correction.employee_id,
        local_date=correction.local_date,
        previous_check_in=correction.previous_check_in,
        previous_check_out=correction.previous_check_out,
        new_check_in=correction.new_check_in,
        new_check_out=correction.new_check_out,
        status=correction.status,
        device_updated=correction.status == CORRECTION_STATUS_APPLIED,
        device_command_uuid=correction.device_command_uuid,
        device_tier=correction.device_tier,
        correction_mode=correction.correction_mode,
        reimport_completed_at=correction.reimport_completed_at,
        error_message=correction.error_message,
        applied_at=correction.applied_at,
    )


@router.get("/capabilities", response_model=CorrectionCapabilitiesRead)
def get_correction_capabilities(
    _privileged: User = Depends(require_privileged_account),
) -> CorrectionCapabilitiesRead:
    caps = probe_correction_capabilities(DeviceService())
    return CorrectionCapabilitiesRead(
        tier=str(caps.get("tier") or "C"),
        record_size=int(caps["record_size"]) if caps.get("record_size") is not None else None,
        supports_selective_delete=bool(caps.get("supports_selective_delete")),
        supports_full_rewrite=bool(caps.get("supports_full_rewrite")),
        supports_write=bool(caps.get("supports_write")),
        strict_device_authority=bool(caps.get("strict_device_authority")),
        correction_allow_db_only_fallback=bool(caps.get("correction_allow_db_only_fallback")),
    )


@router.get("/corrections/{correction_uuid}", response_model=AttendanceAdjustmentRead)
def get_correction_status(
    correction_uuid: str,
    _privileged: User = Depends(require_privileged_account),
    db: Session = Depends(get_db),
) -> AttendanceAdjustmentRead:
    correction = db.execute(
        select(AttendanceCorrection).where(AttendanceCorrection.correction_uuid == correction_uuid)
    ).scalar_one_or_none()
    if correction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction not found.")
    return _adjustment_read(correction)


@router.get("/day/{employee_id}", response_model=DayAdjustmentPreview)
def preview_adjustment_day(
    employee_id: int,
    summary_date: date = Query(..., alias="date"),
    _privileged: User = Depends(require_privileged_account),
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
    responses={202: {"description": "Device correction queued (strict mode, device_pending)."}},
)
def apply_attendance_adjustment(
    payload: AttendanceAdjustRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_privileged_account),
    db: Session = Depends(get_db),
) -> AttendanceAdjustmentRead:
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
    except DeviceLockContentionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AttlogCorrectionNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except AttlogCorrectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if correction.status == CORRECTION_STATUS_DEVICE_PENDING:
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        append_audit_log(
            db,
            actor_user_uuid=user.user_uuid,
            action_type=AUDIT_ACTION_ATTENDANCE_ADJUST,
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

    return _adjustment_read(correction)
