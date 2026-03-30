"""Trigger read-only sync from the biometric device into PostgreSQL."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from zk.exception import ZKError

from app.core.database import get_db
from app.services.attendance_service import run_device_sync, run_user_sync

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
def sync_from_device(db: Session = Depends(get_db)) -> DeviceSyncResponse:
    """
    Pull users and attendance from the terminal (pyzk read-only), backfill missing employees for orphan
    punch codes, and rebuild sessions for SESSION_REBUILD_LOOKBACK_DAYS trailing local days.
    Same effective steps as ``scripts/sync_from_device.py``.
    """
    try:
        u_total, u_ins = run_user_sync(db)
        a_fetch, a_ins, placeholders = run_device_sync(db)
    except ZKError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Device communication error: {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Device connection failed: {exc}",
        ) from exc
    return DeviceSyncResponse(
        users_on_device=u_total,
        new_employees=u_ins,
        attendance_records_fetched=a_fetch,
        new_attendance_logs=a_ins,
        placeholder_employees_created=placeholders,
    )
