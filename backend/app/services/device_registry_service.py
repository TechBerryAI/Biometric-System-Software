"""Device registry and reconciliation helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.device import Device
from app.models.device_user_mapping import DeviceUserMapping
from app.services.device_service import DeviceService


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def ensure_default_device(db: Session, settings: Settings | None = None) -> Device:
    settings = settings or get_settings()
    existing = db.execute(select(Device).where(Device.name == settings.zk_device_id)).scalar_one_or_none()
    if existing is not None:
        existing.ip_address = settings.zk_device_ip
        existing.port = settings.zk_device_port
        existing.timezone = settings.timezone
        return existing
    row = Device(
        name=settings.zk_device_id,
        ip_address=settings.zk_device_ip,
        port=settings.zk_device_port,
        timezone=settings.timezone,
        active=True,
        health_status="UNKNOWN",
    )
    db.add(row)
    db.flush()
    return row


def update_device_health(db: Session, *, status: str, detail: str | None = None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    device = ensure_default_device(db, settings)
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


def reconcile_device_mappings(db: Session, settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    device_users = {user.user_id for user in DeviceService(settings=settings).fetch_users()}
    mapped_users = {
        row[0]
        for row in db.execute(
            select(DeviceUserMapping.device_user_id).where(
                DeviceUserMapping.device_id == settings.zk_device_id,
                DeviceUserMapping.active.is_(True),
            )
        ).all()
        if row[0]
    }
    missing_on_device = sorted(mapped_users - device_users)
    missing_mapping = sorted(device_users - mapped_users)
    return {
        "missing_on_device": len(missing_on_device),
        "missing_mapping": len(missing_mapping),
    }
