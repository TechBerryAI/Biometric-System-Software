"""Operational APIs for audit logs and command queue observability."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_sync_event import DeviceSyncEvent
from app.schemas.audit import AuditLogRead
from app.schemas.device_command import DeviceCommandRead

router = APIRouter(prefix="/ops", tags=["operations"])


@router.get("/audit-logs", response_model=list[AuditLogRead], dependencies=[Depends(require_permissions(Permission.AUDIT_READ))])
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    return list(db.execute(query).scalars().all())


@router.get(
    "/device-commands",
    response_model=list[DeviceCommandRead],
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def list_device_commands(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[DeviceCommand]:
    query = select(DeviceCommand).order_by(DeviceCommand.created_at.desc()).limit(limit)
    if status:
        query = query.where(DeviceCommand.status == status)
    return list(db.execute(query).scalars().all())


@router.get("/metrics", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operational_metrics(db: Session = Depends(get_db)) -> dict[str, int]:
    stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=15)
    queue_depth = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status.in_(
                    [
                        DeviceCommandStatus.PENDING.value,
                        DeviceCommandStatus.RUNNING.value,
                        DeviceCommandStatus.FAILED.value,
                    ]
                )
            )
        ).scalar_one()
        or 0
    )
    stale_commands = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status == DeviceCommandStatus.RUNNING.value,
                DeviceCommand.started_at < stale_cutoff,
            )
        ).scalar_one()
        or 0
    )
    dead_letters = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one()
        or 0
    )
    failing_devices = (
        db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one()
        or 0
    )
    sync_lag_events = (
        db.execute(
            select(func.count()).where(
                DeviceSyncEvent.event_type == "RECONCILIATION",
                DeviceSyncEvent.status == "DRIFT",
            )
        ).scalar_one()
        or 0
    )
    return {
        "queue_depth": int(queue_depth),
        "stale_commands": int(stale_commands),
        "dead_letter_commands": int(dead_letters),
        "failing_devices": int(failing_devices),
        "sync_drift_events": int(sync_lag_events),
    }
