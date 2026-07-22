"""Device registry and reconciliation helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.gateway.router import get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.devices.services.device_service import DeviceService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def list_devices(
    db: Session,
    *,
    branch_id: str | None = None,
    active_only: bool = True,
) -> list[Device]:
    stmt = select(Device)
    if active_only:
        stmt = stmt.where(Device.active.is_(True))
    if branch_id is not None:
        stmt = stmt.where(Device.branch_id == branch_id)
    return list(db.execute(stmt.order_by(Device.id)).scalars().all())


def get_device_by_name(db: Session, device_name: str) -> Device | None:
    return db.execute(select(Device).where(Device.name == device_name)).scalar_one_or_none()


def create_device(
    db: Session,
    *,
    name: str,
    ip_address: str,
    port: int = 4370,
    location: str | None = None,
    timezone: str | None = None,
    branch_id: str | None = None,
    connectivity_mode: str = "both",
    settings: Settings | None = None,
) -> Device:
    settings = settings or get_settings()
    existing = get_device_by_name(db, name)
    if existing is not None:
        raise ValueError(f"Device '{name}' already exists.")
    row = Device(
        device_uuid=str(uuid4()),
        name=name.strip(),
        ip_address=ip_address.strip(),
        port=port,
        location=location,
        timezone=timezone or settings.timezone,
        branch_id=branch_id,
        connectivity_mode=connectivity_mode,
        active=True,
        health_status="UNKNOWN",
        mode="NORMAL",
    )
    db.add(row)
    db.flush()
    db.add(DeviceSyncState(device_id=row.name))
    return row


def update_device(db: Session, device: Device, **fields: Any) -> Device:
    allowed = {
        "name",
        "ip_address",
        "port",
        "location",
        "timezone",
        "branch_id",
        "connectivity_mode",
        "active",
        "mode",
        "capabilities",
    }
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(device, key, value)
    db.flush()
    get_device_gateway().invalidate(device.name)
    return device


def deactivate_device(db: Session, device: Device, *, reason: str | None = None) -> Device:
    device.active = False
    device.health_status = "OFFLINE"
    device.mode = "OFFLINE"
    if reason:
        device.quarantine_reason = reason
    db.flush()
    get_device_gateway().invalidate(device.name)
    return device


def ensure_default_device(db: Session, settings: Settings | None = None) -> Device:
    settings = settings or get_settings()
    existing = db.execute(select(Device).where(Device.name == settings.zk_device_id)).scalar_one_or_none()
    if existing is not None:
        existing.ip_address = settings.zk_device_ip
        existing.port = settings.zk_device_port
        existing.timezone = settings.timezone
        existing.active = True
        # Prefer push+pull so ADMS real-time punches and Celery pull both apply.
        mode = (existing.connectivity_mode or "pull").lower()
        if mode == "pull":
            existing.connectivity_mode = "both"
        for sibling in db.execute(
            select(Device).where(
                Device.ip_address == existing.ip_address,
                Device.id != existing.id,
                Device.active.is_(True),
            )
        ).scalars().all():
            sibling.active = False
            sibling.health_status = "OFFLINE"
            sibling.mode = "OFFLINE"
            sibling.quarantine_reason = sibling.quarantine_reason or "Duplicate IP merged into canonical device"
        return existing
    row = Device(
        name=settings.zk_device_id,
        ip_address=settings.zk_device_ip,
        port=settings.zk_device_port,
        timezone=settings.timezone,
        active=True,
        health_status="UNKNOWN",
        connectivity_mode="both",
    )
    db.add(row)
    db.flush()
    db.add(DeviceSyncState(device_id=row.name))
    for sibling in db.execute(
        select(Device).where(
            Device.ip_address == row.ip_address,
            Device.id != row.id,
            Device.active.is_(True),
        )
    ).scalars().all():
        sibling.active = False
        sibling.health_status = "OFFLINE"
        sibling.mode = "OFFLINE"
        sibling.quarantine_reason = sibling.quarantine_reason or "Duplicate IP merged into canonical device"
    return row


def update_device_health_for_device(
    db: Session,
    device: Device,
    *,
    status: str,
    detail: str | None = None,
) -> None:
    device.health_status = status
    device.last_seen = _utcnow() if status == "ONLINE" else device.last_seen
    if status == "ONLINE":
        if device.mode in {"OFFLINE", "DEGRADED"}:
            device.mode = "NORMAL"
    elif status == "OFFLINE":
        device.mode = "OFFLINE"
    elif status == "DEGRADED":
        if device.mode not in {"QUARANTINED", "OFFLINE"}:
            device.mode = "DEGRADED"
    _ = detail


def update_device_health(db: Session, *, status: str, detail: str | None = None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    device = ensure_default_device(db, settings)
    update_device_health_for_device(db, device, status=status, detail=detail)


def reconcile_device_mappings(
    db: Session,
    device: Device | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    if device is None:
        device = ensure_default_device(db, settings)
    connection = DeviceConnectionConfig.from_device(device, settings)
    device_users = {user.user_id for user in DeviceService(connection=connection).fetch_users()}
    device_id = device.name
    mapped_users = {
        row[0]
        for row in db.execute(
            select(DeviceUserMapping.device_user_id).where(
                DeviceUserMapping.device_id == device_id,
                DeviceUserMapping.active.is_(True),
            )
        ).all()
        if row[0]
    }
    missing_on_device = sorted(mapped_users - device_users)
    missing_mapping = sorted(device_users - mapped_users)

    sync_state = db.execute(
        select(DeviceSyncState).where(DeviceSyncState.device_id == device_id)
    ).scalar_one_or_none()
    if sync_state is None:
        sync_state = DeviceSyncState(device_id=device_id)
        db.add(sync_state)
    sync_state.drift_counts = {
        "missing_on_device": len(missing_on_device),
        "missing_mapping": len(missing_mapping),
    }
    from app.domains.devices.services.drift_service import persist_drift_events

    persist_drift_events(
        db,
        device_id=device_id,
        missing_on_device=missing_on_device,
        missing_mapping=missing_mapping,
        tenant_id=getattr(device, "tenant_id", None),
    )
    return {
        "missing_on_device": len(missing_on_device),
        "missing_mapping": len(missing_mapping),
    }


def reconcile_all_devices(db: Session, settings: Settings | None = None) -> list[dict[str, int | str]]:
    settings = settings or get_settings()
    results: list[dict[str, int | str]] = []
    for device in list_devices(db, active_only=True):
        device_id = device.name
        try:
            counts = reconcile_device_mappings(db, device, settings=settings)
            results.append({"device_id": device_id, **counts})
        except Exception as exc:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("Rollback after reconcile failure failed device=%s", device_id, exc_info=True)
            results.append({"device_id": device_id, "error": str(exc)})
    return results
