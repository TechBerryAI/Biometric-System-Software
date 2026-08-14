"""Trigger read-only sync from the biometric device into PostgreSQL."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from zk.exception import ZKError

from app.ai.cache.redis_cache import AIResponseCache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.attendance.services.attendance_service import run_device_sync_detailed, run_user_sync
from app.domains.devices.services.device_command_service import device_session_lock, wait_for_correction_commands_clear
from app.shared.device_exceptions import DeviceFetchError, DeviceLockContentionError
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.services.device_registry_service import ensure_default_device, update_device_health
from app.domains.devices.services.device_service import DeviceService, format_device_connection_error
from app.domains.devices.services.sync_manager_service import get_or_create_sync_state

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
    skipped_reason: str | None = Field(
        default=None,
        description="Why sync inserted nothing without fetching: correction_active | lock_contention",
    )
    skipped_corrected_punches: int = Field(
        default=0,
        description="Device punches skipped because they fall at/before a mid-day correction guard",
    )
    punches_missing_after_insert: int = Field(
        default=0,
        description="Fetched punches still absent from DB after insert (should be 0)",
    )


@router.post("/device", response_model=DeviceSyncResponse)
def sync_from_device(
    request: Request,
    full: bool = Query(
        True,
        description="Pull all attendance still on the device (default True). Set false only for rare incremental pulls.",
    ),
    user: User = Depends(require_permissions(Permission.SYNC_TRIGGER)),
    db: Session = Depends(get_db),
) -> DeviceSyncResponse:
    """
    Pull users and attendance from the terminal (pyzk read-only), backfill missing employees for orphan
    punch codes, and rebuild sessions for SESSION_REBUILD_LOOKBACK_DAYS trailing local days.

    Defaults to a full device history pull so Sync now never misses punches still stored on the terminal.
    """
    del request, user  # auth + request context still required via Depends
    settings = get_settings()
    registered = ensure_default_device(db, settings)
    connection = DeviceConnectionConfig.from_device(registered, settings)
    device_service = DeviceService(settings=settings, connection=connection)
    if not wait_for_correction_commands_clear(db, registered.name, settings=settings):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Device '{registered.name}' is applying an attendance correction. "
                "Wait a few seconds and retry sync."
            ),
        )
    try:
        with device_session_lock(registered.name, settings):
            u_total, u_ins = run_user_sync(
                db,
                device=device_service,
                settings=settings,
                device_id=registered.name,
            )
            sync_result = run_device_sync_detailed(
                db,
                device=device_service,
                full_resync=full,
                settings=settings,
                device_id=registered.name,
            )
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
    sync_state = get_or_create_sync_state(db, registered.name)
    now = datetime.now(ZoneInfo("UTC"))
    sync_state.last_user_sync_at = now
    sync_state.last_attendance_sync_at = now
    sync_state.sync_generation += 1
    cache = AIResponseCache(settings)
    cache.delete_prefix("ai:management:")
    cache.delete_prefix("ai:report:")
    cache.delete_prefix("ai:copilot:")
    cache.delete_prefix("ai:anomaly:")
    response = DeviceSyncResponse(
        users_on_device=u_total,
        new_employees=u_ins,
        attendance_records_fetched=sync_result.fetched,
        new_attendance_logs=sync_result.inserted,
        placeholder_employees_created=sync_result.placeholders,
        skipped_reason=sync_result.skipped_reason,
        skipped_corrected_punches=sync_result.skipped_corrected_punches,
        punches_missing_after_insert=sync_result.punches_missing_after_insert,
    )
    db.commit()
    return response
