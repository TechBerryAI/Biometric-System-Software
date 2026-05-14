"""Governance endpoints: maintenance/freeze/quarantine and approvals."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.device import Device
from app.models.operator_approval import OperatorApproval
from app.models.system_control_state import SystemControlState
from app.models.user import User
from app.services.audit_service import append_audit_log
from app.services.system_governance_service import ensure_control_state

router = APIRouter(prefix="/governance", tags=["governance"])


class ToggleModeRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=1000)


class QuarantineRequest(BaseModel):
    device_name: str
    reason: str = Field(min_length=3, max_length=1000)


class ApprovalDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=1000)


@router.get("/state", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def governance_state(db: Session = Depends(get_db)) -> dict[str, object]:
    row = ensure_control_state(db)
    return {
        "maintenance_mode": row.maintenance_mode,
        "emergency_freeze_mode": row.emergency_freeze_mode,
        "changed_by": row.changed_by,
        "change_reason": row.change_reason,
        "updated_at": row.updated_at,
    }


@router.post("/maintenance", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def set_maintenance_mode(
    payload: ToggleModeRequest,
    request: Request,
    actor: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = ensure_control_state(db)
    row.maintenance_mode = payload.enabled
    row.changed_by = actor.user_uuid
    row.change_reason = payload.reason
    append_audit_log(
        db,
        actor_user_uuid=actor.user_uuid,
        action_type="MAINTENANCE_MODE_CHANGED",
        entity_type="governance",
        entity_id="global",
        new_state={"enabled": payload.enabled, "reason": payload.reason},
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"maintenance_mode": row.maintenance_mode}


@router.post("/emergency-freeze", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def set_emergency_freeze(
    payload: ToggleModeRequest,
    request: Request,
    actor: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = ensure_control_state(db)
    row.emergency_freeze_mode = payload.enabled
    row.changed_by = actor.user_uuid
    row.change_reason = payload.reason
    append_audit_log(
        db,
        actor_user_uuid=actor.user_uuid,
        action_type="EMERGENCY_FREEZE_CHANGED",
        entity_type="governance",
        entity_id="global",
        new_state={"enabled": payload.enabled, "reason": payload.reason},
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"emergency_freeze_mode": row.emergency_freeze_mode}


@router.post("/quarantine", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def quarantine_device(
    payload: QuarantineRequest,
    request: Request,
    actor: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    device = db.execute(select(Device).where(Device.name == payload.device_name)).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    device.mode = "QUARANTINED"
    device.quarantine_reason = payload.reason
    append_audit_log(
        db,
        actor_user_uuid=actor.user_uuid,
        action_type="DEVICE_QUARANTINED",
        entity_type="device",
        entity_id=device.device_uuid,
        new_state={"name": device.name, "reason": payload.reason},
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"status": "QUARANTINED"}


@router.post("/approvals/request", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def request_approval(
    payload: QuarantineRequest,
    request: Request,
    actor: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = OperatorApproval(
        approval_uuid=uuid4().hex,
        action_type="DEVICE_QUARANTINE",
        target_entity=payload.device_name,
        requested_by=actor.user_uuid,
        status="PENDING",
        requires_dual_confirmation=True,
        request_details={"reason": payload.reason},
    )
    db.add(row)
    append_audit_log(
        db,
        actor_user_uuid=actor.user_uuid,
        action_type="APPROVAL_REQUESTED",
        entity_type="approval",
        entity_id=row.approval_uuid,
        new_state={"action_type": row.action_type, "target_entity": row.target_entity},
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"approval_uuid": row.approval_uuid}


@router.post("/approvals/{approval_uuid}", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def resolve_approval(
    approval_uuid: str,
    payload: ApprovalDecision,
    request: Request,
    actor: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.execute(select(OperatorApproval).where(OperatorApproval.approval_uuid == approval_uuid)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    row.status = "APPROVED" if payload.approve else "REJECTED"
    row.approved_by = actor.user_uuid
    row.approval_details = {"note": payload.note}
    row.completed_at = datetime.now(ZoneInfo("UTC"))
    append_audit_log(
        db,
        actor_user_uuid=actor.user_uuid,
        action_type="APPROVAL_RESOLVED",
        entity_type="approval",
        entity_id=row.approval_uuid,
        new_state={"status": row.status, "note": payload.note},
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return {"status": row.status}
