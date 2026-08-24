"""Operational APIs for command queue observability."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.operator_access import is_operator_account
from app.core.security import Permission, get_current_user, require_permissions
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.ops.models.system_control_state import SystemControlState
from app.domains.auth.models.user import User
from app.domains.devices.schemas import DeviceCommandRead
from app.domains.devices.services.device_command_service import INTERNAL_COMMAND_TYPES, reprocess_device_command
from app.domains.devices.services.device_registry_service import (
    ensure_default_device,
    update_device_health_for_device,
)
from app.domains.attendance.services.incomplete_day_metrics import (
    count_incomplete_attendance_days,
    list_incomplete_attendance_days,
)
from app.domains.devices.models.device_sync_state import DeviceSyncState

router = APIRouter(prefix="/ops", tags=["operations"])


class OperationalMetricsRead(BaseModel):
    queue_depth: int
    stale_commands: int
    dead_letter_commands: int
    failing_devices: int
    sync_drift_events: int
    verification_failures: int
    reconciliation_pending: int
    replay_recovered_success: int
    lock_contention_events: int
    commands_currently_verifying: int
    snapshot_events_last_24h: int
    quarantined_devices: int
    emergency_freeze_active: int
    device_health_status: str
    device_ip: str
    device_port: int
    device_auto_sync_enabled: bool
    incomplete_attendance_days: int = 0
    last_attendance_sync_at: datetime | None = None
    incomplete_attendance_samples: list[dict[str, object]] = []
    attendance_sync_stale: bool = False
    device_connectivity_mode: str = "both"
    device_clock_drift_seconds: float | None = None


@router.get(
    "/device-commands",
    response_model=list[DeviceCommandRead],
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def list_device_commands(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeviceCommand]:
    query = select(DeviceCommand).order_by(DeviceCommand.created_at.desc()).limit(limit)
    if status:
        query = query.where(DeviceCommand.status == status)
    rows = list(db.execute(query).scalars().all())
    if not is_operator_account(user):
        rows = [row for row in rows if row.command_type not in INTERNAL_COMMAND_TYPES]
    return rows


@router.post(
    "/device-commands/{command_uuid}/process",
    response_model=DeviceCommandRead,
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def process_device_command_now(
    command_uuid: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceCommand:
    command = db.execute(select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)).scalar_one_or_none()
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    if command.command_type in INTERNAL_COMMAND_TYPES and not is_operator_account(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    try:
        command = reprocess_device_command(db, command_uuid, worker_id="api-ops-reprocess")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.refresh(command)
    return command


@router.get(
    "/metrics",
    response_model=OperationalMetricsRead,
    dependencies=[Depends(require_permissions(Permission.METRICS_READ))],
)
def operational_metrics(db: Session = Depends(get_db)) -> OperationalMetricsRead:
    settings = get_settings()
    # Canonicalize default device + deactivate same-IP duplicates before health counts.
    registered_device = ensure_default_device(db, settings=settings)
    db.commit()
    db.refresh(registered_device)

    stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=15)
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
    dead_letters = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one()
        or 0
    )
    failing_devices = (
        db.execute(
            select(func.count()).where(
                Device.active.is_(True),
                Device.health_status.in_(["OFFLINE", "DEGRADED"]),
            )
        ).scalar_one()
        or 0
    )
    verification_failures = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.verification_status == "FAILED",
            )
        ).scalar_one()
        or 0
    )
    verification_latency_events = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.VERIFYING.value)).scalar_one()
        or 0
    )
    quarantined_devices = db.execute(select(func.count()).where(Device.mode == "QUARANTINED")).scalar_one() or 0
    emergency_freeze = (
        db.execute(
            select(func.count()).where(
                SystemControlState.singleton_key == "global",
                SystemControlState.emergency_freeze_mode.is_(True),
            )
        ).scalar_one()
        or 0
    )
    incomplete_days = count_incomplete_attendance_days(db, lookback_days=30, settings=settings)
    incomplete_samples = list_incomplete_attendance_days(db, lookback_days=14, limit=10, settings=settings)
    sync_state = db.execute(
        select(DeviceSyncState).where(DeviceSyncState.device_id == registered_device.name)
    ).scalar_one_or_none()
    last_sync = sync_state.last_attendance_sync_at if sync_state else None
    clock_drift: float | None = None
    if sync_state and isinstance(sync_state.drift_counts, dict):
        raw_drift = sync_state.drift_counts.get("clock_drift_seconds")
        try:
            clock_drift = float(raw_drift) if raw_drift is not None else None
        except (TypeError, ValueError):
            clock_drift = None
    # Stale if no successful sync within 3× poll interval (or 10 minutes minimum).
    stale_after = timedelta(seconds=max(settings.device_poll_interval_seconds * 3, 600))
    now_utc = datetime.now(ZoneInfo("UTC"))
    if last_sync is None:
        attendance_sync_stale = bool(settings.device_auto_sync_enabled)
    else:
        aware = last_sync if last_sync.tzinfo is not None else last_sync.replace(tzinfo=ZoneInfo("UTC"))
        attendance_sync_stale = (now_utc - aware.astimezone(ZoneInfo("UTC"))) > stale_after
        # Self-heal: a recent successful sync proves the device is up — don't leave UI on Offline.
        if (
            settings.device_auto_sync_enabled
            and not attendance_sync_stale
            and (registered_device.health_status or "").upper() in {"OFFLINE", "DEGRADED", "UNKNOWN"}
        ):
            update_device_health_for_device(
                db, registered_device, status="ONLINE", detail="metrics_heal_from_recent_sync"
            )
            db.commit()
            db.refresh(registered_device)
            failing_devices = (
                db.execute(
                    select(func.count()).where(
                        Device.active.is_(True),
                        Device.health_status.in_(["OFFLINE", "DEGRADED"]),
                    )
                ).scalar_one()
                or 0
            )
    device_health_status = (
        "MANUAL" if not settings.device_auto_sync_enabled else registered_device.health_status
    )
    effective_failing_devices = (
        0 if not settings.device_auto_sync_enabled else int(failing_devices)
    )
    return OperationalMetricsRead(
        queue_depth=int(queue_depth),
        stale_commands=int(stale_commands),
        dead_letter_commands=int(dead_letters),
        failing_devices=effective_failing_devices,
        sync_drift_events=0,
        verification_failures=int(verification_failures),
        reconciliation_pending=0,
        replay_recovered_success=0,
        lock_contention_events=0,
        commands_currently_verifying=int(verification_latency_events),
        snapshot_events_last_24h=0,
        quarantined_devices=int(quarantined_devices),
        emergency_freeze_active=int(emergency_freeze),
        device_health_status=device_health_status,
        device_ip=registered_device.ip_address,
        device_port=registered_device.port,
        device_auto_sync_enabled=settings.device_auto_sync_enabled,
        incomplete_attendance_days=incomplete_days,
        last_attendance_sync_at=last_sync,
        incomplete_attendance_samples=incomplete_samples,
        attendance_sync_stale=attendance_sync_stale,
        device_connectivity_mode=(registered_device.connectivity_mode or "both"),
        device_clock_drift_seconds=clock_drift,
    )
