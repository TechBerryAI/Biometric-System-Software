"""Trigger read-only sync from the biometric device into PostgreSQL."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from zk.exception import ZKError

from app.ai.cache.redis_cache import AIResponseCache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.user import User
from app.services.attendance_service import run_device_sync, run_user_sync
from app.services.device_command_service import device_session_lock, wait_for_correction_commands_clear
from app.services.device_exceptions import DeviceFetchError, DeviceLockContentionError
from app.services.device_registry_service import update_device_health
from app.services.device_service import format_device_connection_error

router = APIRouter(prefix="/sync", tags=["sync"])


class DeviceSyncResponse(BaseModel):
    users_on_device: int = Field(description="Users returned by get_users()")
    new_employees: int = Field(description="User upserts touching the employees table (driver rowcount; see logs)")
    attendance_records_fetched: int = Field(description="Raw rows from get_attendance()")
    new_attendance_logs: int = Field(description="New log rows inserted (idempotent)")
    placeholder_employees_created: int = Field(
        default=0,
        description="New employees created from orphan punch codes (no prior device_user_id row)",
    )


@router.post("/device", response_model=DeviceSyncResponse)
def sync_from_device(
    request: Request,
    full: bool = Query(False, description="Ignore incremental sync floor and pull all device attendance"),
    user: User = Depends(require_permissions(Permission.SYNC_TRIGGER)),
    db: Session = Depends(get_db),
) -> DeviceSyncResponse:
    """
    Pull users and attendance from the terminal (pyzk read-only), backfill missing employees for orphan
    punch codes, and rebuild sessions for SESSION_REBUILD_LOOKBACK_DAYS trailing local days.
    Same effective steps as ``scripts/sync_from_device.py``.
    """
    del request, user  # auth + request context still required via Depends
    settings = get_settings()
    if not wait_for_correction_commands_clear(db, settings.zk_device_id, settings=settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Device '{settings.zk_device_id}' is applying an attendance correction. "
                "Wait a few seconds and retry sync."
            ),
        )
    try:
        with device_session_lock(settings.zk_device_id, settings):
            u_total, u_ins = run_user_sync(db, settings=settings)
            a_fetch, a_ins, placeholders = run_device_sync(db, full_resync=full, settings=settings)
    except DeviceLockContentionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (ZKError, DeviceFetchError) as exc:
        detail = format_device_connection_error(exc, settings=settings)
        update_device_health(db, status="OFFLINE", detail=detail, settings=settings)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc
    except OSError as exc:
        detail = format_device_connection_error(exc, settings=settings)
        update_device_health(db, status="OFFLINE", detail=detail, settings=settings)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc

    update_device_health(db, status="ONLINE", detail="sync_ok", settings=settings)
    cache = AIResponseCache(settings)
    cache.delete_prefix("ai:management:")
    cache.delete_prefix("ai:report:")
    cache.delete_prefix("ai:copilot:")
    cache.delete_prefix("ai:anomaly:")
    response = DeviceSyncResponse(
        users_on_device=u_total,
        new_employees=u_ins,
        attendance_records_fetched=a_fetch,
        new_attendance_logs=a_ins,
        placeholder_employees_created=placeholders,
    )
    db.commit()
    return response
