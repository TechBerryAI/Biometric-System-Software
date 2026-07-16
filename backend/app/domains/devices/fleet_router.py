"""Fleet device management REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, User, get_current_user, require_permissions
from app.domains.devices.services.device_manager_service import DeviceManagerService

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=1, max_length=128)
    port: int = Field(default=4370, ge=1, le=65535)
    location: str | None = None
    timezone: str | None = None
    branch_id: str | None = None
    connectivity_mode: str = Field(default="pull", pattern="^(pull|push|both)$")


class DeviceUpdateRequest(BaseModel):
    ip_address: str | None = Field(default=None, min_length=1, max_length=128)
    port: int | None = Field(default=None, ge=1, le=65535)
    location: str | None = None
    timezone: str | None = None
    branch_id: str | None = None
    connectivity_mode: str | None = Field(default=None, pattern="^(pull|push|both)$")
    active: bool | None = None


class DeviceResponse(BaseModel):
    id: int
    device_uuid: str
    name: str
    ip_address: str
    port: int
    location: str | None
    timezone: str
    branch_id: str | None
    connectivity_mode: str
    firmware_version: str | None
    serial_number: str | None
    active: bool
    health_status: str
    mode: str
    last_seen: datetime | None
    config_version: int

    model_config = {"from_attributes": True}


class DeviceCommandRequest(BaseModel):
    command_type: str = Field(
        description="RESTART, SYNC_TIME, REMOTE_CONFIG, REMOTE_ENROLL, REMOTE_DELETE, FORCE_SYNC, FIRMWARE_CHECK"
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class DeviceCommandResponse(BaseModel):
    command_uuid: str
    device_id: str
    command_type: str
    status: str


def _to_response(device: Any) -> DeviceResponse:
    return DeviceResponse.model_validate(device)


@router.get("", response_model=list[DeviceResponse])
def list_devices(
    branch_id: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> list[DeviceResponse]:
    del user
    manager = DeviceManagerService(db)
    return [_to_response(d) for d in manager.list_fleet(branch_id=branch_id, active_only=active_only)]


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    body: DeviceCreateRequest,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> DeviceResponse:
    del user
    manager = DeviceManagerService(db)
    try:
        device = manager.register_device(**body.model_dump())
        db.commit()
        db.refresh(device)
        return _to_response(device)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{device_name}", response_model=DeviceResponse)
def get_device(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> DeviceResponse:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    return _to_response(device)


@router.patch("/{device_name}", response_model=DeviceResponse)
def update_device(
    device_name: str,
    body: DeviceUpdateRequest,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> DeviceResponse:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    updated = manager.update_device_record(device, **body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(updated)
    return _to_response(updated)


@router.delete("/{device_name}", response_model=DeviceResponse)
def deactivate_device(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> DeviceResponse:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    result = manager.deactivate(device, reason="Deactivated via API")
    db.commit()
    db.refresh(result)
    return _to_response(result)


@router.get("/{device_name}/health")
def device_health(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    return manager.get_health(device)


@router.post("/{device_name}/probe")
def probe_device(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    result = manager.probe_health(device)
    db.commit()
    return result


@router.post("/{device_name}/sync")
def sync_device_endpoint(
    device_name: str,
    full: bool = Query(default=True),
    user: User = Depends(require_permissions(Permission.SYNC_TRIGGER)),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    result = manager.sync_device(device, full_resync=full)
    db.commit()
    return result


@router.get("/{device_name}/config")
def get_config(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del user
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    return manager.get_config(device)


@router.put("/{device_name}/config")
def update_config(
    device_name: str,
    config: dict[str, Any],
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    manager.update_config(device, config, initiated_by=user.user_uuid)
    db.commit()
    return manager.get_config(device)


@router.post("/{device_name}/commands", response_model=DeviceCommandResponse)
def enqueue_command(
    device_name: str,
    body: DeviceCommandRequest,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> DeviceCommandResponse:
    manager = DeviceManagerService(db)
    device = manager.get_device(device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    try:
        command = manager.enqueue_command(
            device,
            body.command_type,
            body.payload,
            initiated_by=user.user_uuid,
        )
        db.commit()
        return DeviceCommandResponse(
            command_uuid=command.command_uuid,
            device_id=command.device_id,
            command_type=command.command_type,
            status=command.status,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
