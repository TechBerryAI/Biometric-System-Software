"""Inbound ADMS push gateway HTTP endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.devices.gateway.device_auth import DeviceAuthService, rotate_device_secret
from app.domains.devices.gateway.push_connector import PushConnector
from app.domains.devices.gateway.router import get_device_gateway
from app.domains.devices.services.device_registry_service import update_device_health_for_device
from app.domains.devices.services.sync_manager_service import sync_device
from app.core.security import Permission, User, require_permissions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices/gateway", tags=["device-gateway"])


class PushPayload(BaseModel):
    users: list[dict[str, Any]] | None = None
    attendance: list[dict[str, Any]] | None = None
    trigger_sync: bool = Field(default=True, description="Process buffered data immediately")


class PushResponse(BaseModel):
    accepted: bool
    device_id: str
    buffered: dict[str, int]
    sync: dict[str, int | str | None] | None = None


@router.post("/push/{device_id}", response_model=PushResponse)
async def receive_device_push(
    device_id: str,
    request: Request,
    body: PushPayload,
    x_device_timestamp: str = Header(alias="X-Device-Timestamp"),
    x_device_nonce: str = Header(alias="X-Device-Nonce"),
    x_device_signature: str = Header(alias="X-Device-Signature"),
    x_device_secret: str | None = Header(default=None, alias="X-Device-Secret"),
    db: Session = Depends(get_db),
) -> PushResponse:
    """ADMS inbound endpoint — devices push attendance and user metadata."""
    raw_body = await request.body()
    auth = DeviceAuthService()
    device, error = auth.authenticate_push_request(
        db,
        device_id=device_id,
        timestamp=x_device_timestamp,
        nonce=x_device_nonce,
        signature=x_device_signature,
        body=raw_body,
        device_secret=x_device_secret,
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error or "Unauthorized")

    connection = get_device_gateway().connection_for_device(device)
    connector = PushConnector(connection, device.offline_buffer)
    buffered = connector.ingest_push_payload(body.model_dump(exclude_none=True))
    device.offline_buffer = connector.buffer
    update_device_health_for_device(db, device, status="ONLINE", detail="push_received")

    sync_result = None
    if body.trigger_sync:
        try:
            # Persist buffer onto the device row before sync so PushConnector reads it.
            db.flush()
            sync_result = sync_device(db, device, full_resync=False)
            missing = int(sync_result.get("punches_missing_after_insert") or 0)
            if sync_result.get("skipped"):
                # Lock/correction deferral — keep buffer for a later attempt.
                logger.warning(
                    "Push sync deferred for %s; retaining offline_buffer",
                    device_id,
                )
            elif missing > 0:
                # Insert/reconcile incomplete — never drop punches from the buffer.
                logger.error(
                    "Push sync for %s left %s punches missing in DB; retaining offline_buffer",
                    device_id,
                    missing,
                )
            else:
                connector.clear_buffer()
                device.offline_buffer = None
        except Exception:
            # Leave offline_buffer intact so punches are not discarded.
            logger.exception("Push sync failed for %s; retaining offline_buffer", device_id)
            db.commit()
            raise

    db.commit()
    return PushResponse(accepted=True, device_id=device_id, buffered=buffered, sync=sync_result)


class RotateSecretResponse(BaseModel):
    device_id: str
    secret: str


@router.post("/{device_id}/rotate-secret", response_model=RotateSecretResponse)
def rotate_secret(
    device_id: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> RotateSecretResponse:
    del user
    from app.domains.devices.services.device_registry_service import get_device_by_name

    device = get_device_by_name(db, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_id}' not found.")
    secret, _ = rotate_device_secret(db, device)
    db.commit()
    return RotateSecretResponse(device_id=device_id, secret=secret)
