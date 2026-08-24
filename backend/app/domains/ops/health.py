"""Health probe endpoints (liveness and dependency checks)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from redis import Redis
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.core import device_policy
from app.core.app_timezone import local_today
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.devices.services.device_registry_service import (
    device_service_for,
    ensure_default_device,
    update_device_health,
)
from app.domains.ops.services.sync_state_metrics import (
    count_reconciliation_completed,
    count_reconciliation_pending,
    sum_lock_contention_events,
)

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health() -> dict[str, str]:
    tz_name = settings.resolved_timezone()
    return {
        "status": "ok",
        "service": settings.app_name,
        "device_writes": "enabled" if device_policy.DEVICE_WRITES_ENABLED else "disabled",
        "timezone": tz_name,
        "local_today": local_today(tz_name).isoformat(),
    }


@router.get("/health/db", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/health/redis", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_redis() -> dict[str, str]:
    client = Redis.from_url(str(settings.redis_url), socket_timeout=3, socket_connect_timeout=3)
    client.ping()
    return {"status": "ok"}


@router.get("/health/devices", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_devices(db: Session = Depends(get_db)) -> dict[str, object]:
    from app.domains.devices.services.device_command_service import device_session_lock
    from app.shared.device_exceptions import DeviceLockContentionError

    registered = ensure_default_device(db, settings=settings)
    device = device_service_for(db, device_name=registered.name, settings=settings)
    try:
        with device_session_lock(registered.name, settings, blocking_timeout=0):
            ok, detail = device.check_connection()
            fingerprint = device.detect_firmware_fingerprint()
    except DeviceLockContentionError:
        return {
            "status": "ok",
            "detail": "device_busy_skip_probe",
            "failing_devices": 0,
            "firmware_version": registered.firmware_version,
            "device_mode": registered.mode,
            "skipped_reason": "device_lock_busy",
        }
    status = "ONLINE" if ok else "OFFLINE"
    update_device_health(db, status=status, detail=detail, settings=settings)
    registered.firmware_version = fingerprint.get("firmware_version")
    registered.serial_number = fingerprint.get("serial_number")
    registered.capabilities = {"platform": fingerprint.get("platform"), "supports_user_write": True}
    db.commit()
    failing_devices = (
        db.execute(
            select(func.count()).where(
                Device.active.is_(True),
                Device.health_status.in_(["OFFLINE", "DEGRADED"]),
            )
        ).scalar_one()
        or 0
    )
    return {
        "status": "ok" if ok else "degraded",
        "detail": detail,
        "failing_devices": int(failing_devices),
        "firmware_version": fingerprint.get("firmware_version"),
        "device_mode": registered.mode,
    }


@router.get("/health/ai", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_ai() -> dict[str, str]:
    if not settings.xai_api_key:
        return {"status": "degraded", "detail": "XAI_API_KEY not configured"}
    return {"status": "ok"}


@router.get("/health/queue", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_queue(db: Session = Depends(get_db)) -> dict[str, int]:
    stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=settings.command_stale_minutes)
    queue_depth = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status.in_(
                    [
                        DeviceCommandStatus.PENDING.value,
                        DeviceCommandStatus.RUNNING.value,
                        DeviceCommandStatus.RETRYING.value,
                        DeviceCommandStatus.VERIFYING.value,
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
                DeviceCommand.status.in_([DeviceCommandStatus.RUNNING.value, DeviceCommandStatus.VERIFYING.value]),
                or_(
                    DeviceCommand.heartbeat_at < stale_cutoff,
                    and_(DeviceCommand.heartbeat_at.is_(None), DeviceCommand.started_at < stale_cutoff),
                ),
            )
        ).scalar_one()
        or 0
    )
    dead_letter = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one()
        or 0
    )
    verification_failures = (
        db.execute(select(func.count()).where(DeviceCommand.verification_status == "FAILED")).scalar_one() or 0
    )
    return {
        "queue_depth": int(queue_depth),
        "stale_commands": int(stale_commands),
        "dead_letter_commands": int(dead_letter),
        "verification_failures": int(verification_failures),
        "reconciliation_pending": count_reconciliation_pending(db),
        "lock_contention_events": sum_lock_contention_events(db),
    }


@router.get("/health/reconciliation", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_reconciliation(db: Session = Depends(get_db)) -> dict[str, int]:
    return {
        "pending_jobs": count_reconciliation_pending(db),
        "completed_jobs": count_reconciliation_completed(db),
    }
