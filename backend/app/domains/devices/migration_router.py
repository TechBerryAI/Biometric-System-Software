"""Replacement-device inspect and employee metadata migration API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.devices.cutover import ReplacementHardwareError
from app.domains.devices.services.device_migration_service import (
    create_preflight,
    execute_migration,
    get_migration,
    inspect_device,
    last_inspect_snapshot,
    migration_to_dict,
    retry_failed,
    run_dry_run,
)
from app.domains.devices.services.device_registry_service import get_device_by_name
from app.shared.device_exceptions import DeviceLockContentionError

router = APIRouter(prefix="/devices", tags=["device-migration"])


class PreflightRequest(BaseModel):
    include_departed: bool = False


class DryRunRequest(BaseModel):
    include_departed: bool = False
    migration_id: str | None = None


class ExecuteRequest(BaseModel):
    dry_run_id: str = Field(min_length=1)
    confirm_target_device_name: str = Field(min_length=1)
    confirm_target_ip: str = Field(min_length=1)
    approve_update_user_ids: list[str] = Field(default_factory=list)


class RetryRequest(BaseModel):
    confirm_target_device_name: str = Field(min_length=1)
    confirm_target_ip: str = Field(min_length=1)


def _device_or_404(db: Session, device_name: str):
    device = get_device_by_name(db, device_name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device '{device_name}' not found.")
    return device


def _http_cutover(exc: Exception) -> HTTPException:
    if isinstance(exc, ReplacementHardwareError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, DeviceLockContentionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_name}/inspect")
def inspect_endpoint(
    device_name: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del user
    device = _device_or_404(db, device_name)
    try:
        snapshot = inspect_device(db, device)
        db.commit()
        return snapshot
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise _http_cutover(exc) from exc


@router.post("/{device_name}/migration/preflight")
def preflight_endpoint(
    device_name: str,
    body: PreflightRequest | None = None,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = _device_or_404(db, device_name)
    payload = body or PreflightRequest()
    try:
        migration = create_preflight(
            db,
            device,
            include_departed=payload.include_departed,
            created_by=user.user_uuid,
        )
        db.commit()
        db.refresh(migration)
        return migration_to_dict(migration, include_items=False)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise _http_cutover(exc) from exc


@router.post("/{device_name}/migration/dry-run")
def dry_run_endpoint(
    device_name: str,
    body: DryRunRequest | None = None,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = _device_or_404(db, device_name)
    payload = body or DryRunRequest()
    try:
        migration = run_dry_run(
            db,
            device,
            include_departed=payload.include_departed,
            created_by=user.user_uuid,
            migration_uuid=payload.migration_id,
        )
        db.commit()
        db.refresh(migration)
        return migration_to_dict(migration)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise _http_cutover(exc) from exc


@router.post("/{device_name}/migration/execute")
def execute_endpoint(
    device_name: str,
    body: ExecuteRequest,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = _device_or_404(db, device_name)
    try:
        migration = execute_migration(
            db,
            device,
            body.dry_run_id,
            confirm_target_device_name=body.confirm_target_device_name,
            confirm_target_ip=body.confirm_target_ip,
            approved_by=user.user_uuid,
            approve_update_user_ids=body.approve_update_user_ids,
        )
        db.commit()
        db.refresh(migration)
        return migration_to_dict(migration)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise _http_cutover(exc) from exc


@router.get("/{device_name}/migration/{migration_id}")
def get_migration_endpoint(
    device_name: str,
    migration_id: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del user
    _device_or_404(db, device_name)
    try:
        migration = get_migration(db, device_name, migration_id)
        return migration_to_dict(migration)
    except Exception as exc:  # noqa: BLE001
        raise _http_cutover(exc) from exc


@router.get("/{device_name}/migration/{migration_id}/report")
def get_migration_report_endpoint(
    device_name: str,
    migration_id: str,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    del user
    _device_or_404(db, device_name)
    try:
        migration = get_migration(db, device_name, migration_id)
        payload = migration_to_dict(migration)
        return {
            "migration_id": payload["migration_id"],
            "status": payload["status"],
            "preflight_summary": payload["preflight_summary"],
            "report": payload["report"],
            "items": payload["items"],
            "fingerprint_next_step": payload["fingerprint_next_step"],
            "last_inspect": last_inspect_snapshot(_device_or_404(db, device_name)),
        }
    except Exception as exc:  # noqa: BLE001
        raise _http_cutover(exc) from exc


@router.post("/{device_name}/migration/{migration_id}/retry-failed")
def retry_failed_endpoint(
    device_name: str,
    migration_id: str,
    body: RetryRequest,
    user: User = Depends(require_permissions(Permission.DEVICE_MANAGE)),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = _device_or_404(db, device_name)
    try:
        migration = retry_failed(
            db,
            device,
            migration_id,
            confirm_target_device_name=body.confirm_target_device_name,
            confirm_target_ip=body.confirm_target_ip,
            approved_by=user.user_uuid,
        )
        db.commit()
        db.refresh(migration)
        return migration_to_dict(migration)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise _http_cutover(exc) from exc
