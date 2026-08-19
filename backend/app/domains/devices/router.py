"""Trigger read-only sync from the biometric device into PostgreSQL."""

from __future__ import annotations

from typing import Any, NoReturn

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.devices.services.device_sync_runner import execute_device_sync
from app.shared.device_exceptions import DeviceFetchError, DeviceLockContentionError
from app.workers.celery_app import celery_app
from app.workers.tasks import run_manual_device_sync

router = APIRouter(prefix="/sync", tags=["sync"])
logger = get_logger("devices.sync")


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


class DeviceSyncQueuedResponse(BaseModel):
    accepted: bool = True
    task_id: str
    status: str = "queued"


class DeviceSyncJobStatus(BaseModel):
    task_id: str
    state: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _raise_sync_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, DeviceLockContentionError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, DeviceFetchError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    raise exc


def _enqueue_manual_sync(full_resync: bool) -> JSONResponse | None:
    try:
        job = run_manual_device_sync.apply_async(kwargs={"full_resync": full_resync})
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual_sync_enqueue_failed", error=str(exc))
        return None
    payload = DeviceSyncQueuedResponse(task_id=str(job.id)).model_dump()
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=payload)


@router.post("/device", response_model=None)
def sync_from_device(
    request: Request,
    full: bool = Query(
        True,
        description="Pull all attendance still on the device (default True). Set false only for rare incremental pulls.",
    ),
    wait: bool = Query(
        True,
        description=(
            "If true, run the pull in this HTTP request. If false, enqueue Celery and return 202 "
            "so reverse proxies with a 60s timeout (nginx on :80) do not 504."
        ),
    ),
    user: User = Depends(require_permissions(Permission.SYNC_TRIGGER)),
    db: Session = Depends(get_db),
) -> DeviceSyncResponse | JSONResponse:
    """
    Pull users and attendance from the terminal (pyzk read-only), backfill missing employees for orphan
    punch codes, and rebuild sessions for SESSION_REBUILD_LOOKBACK_DAYS trailing local days.

    Defaults to a full device history pull so Sync now never misses punches still stored on the terminal.
    Pass wait=false behind nginx/IIS so the browser is not held for the entire ZK dump.
    """
    del request, user
    settings = get_settings()
    if not wait:
        queued = _enqueue_manual_sync(full)
        if queued is not None:
            return queued
    try:
        payload = execute_device_sync(db, settings=settings, full_resync=full)
    except (DeviceLockContentionError, DeviceFetchError) as exc:
        _raise_sync_http_error(exc)
    return DeviceSyncResponse.model_validate(payload)


@router.get("/jobs/{task_id}", response_model=DeviceSyncJobStatus)
def get_manual_sync_job(
    task_id: str,
    user: User = Depends(require_permissions(Permission.SYNC_TRIGGER)),
) -> DeviceSyncJobStatus:
    """Poll Celery status for a Sync now job started with wait=false."""
    del user
    job = AsyncResult(task_id, app=celery_app)
    state = str(job.state or "PENDING")
    raw = job.result
    error: str | None = None
    result: dict[str, Any] | None = None
    if isinstance(raw, dict):
        result = raw
        if raw.get("ok") is False:
            error = str(raw.get("error") or "Sync failed")
    elif state == "FAILURE":
        error = str(raw) if raw else "Sync failed"
    return DeviceSyncJobStatus(task_id=task_id, state=state, result=result, error=error)
