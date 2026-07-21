"""Device heartbeat and connectivity probing."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.services.device_registry_service import update_device_health_for_device

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def probe_device_heartbeat(
    db: Session,
    device: Device,
    *,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> dict[str, object]:
    """Probe a single device and update health status."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    device_id = device.name
    try:
        ok, detail = gateway.probe_device(device)
        status = "ONLINE" if ok else "OFFLINE"
        update_device_health_for_device(db, device, status=status, detail=detail)
        if ok:
            fingerprint = gateway.get_connector(device).detect_firmware_fingerprint()
            fw = fingerprint.get("firmware_version")
            if fw and fw != "unknown":
                device.firmware_version = str(fw)
            serial = fingerprint.get("serial_number")
            if serial:
                device.serial_number = str(serial)
        return {"device_id": device_id, "online": ok, "detail": detail, "probed_at": _utcnow().isoformat()}
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Rollback after heartbeat failure failed device=%s", device_id, exc_info=True)
        logger.warning("Heartbeat probe failed for %s: %s", device_id, exc)
        try:
            update_device_health_for_device(db, device, status="OFFLINE", detail=str(exc))
        except Exception:  # noqa: BLE001
            logger.debug("Health update after heartbeat failure failed device=%s", device_id, exc_info=True)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"device_id": device_id, "online": False, "detail": str(exc), "probed_at": _utcnow().isoformat()}


def probe_all_devices(
    db: Session,
    *,
    branch_id: str | None = None,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> list[dict[str, object]]:
    """Probe all active pull-mode devices."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    results: list[dict[str, object]] = []
    for device in gateway.list_pull_devices(db, branch_id=branch_id):
        results.append(probe_device_heartbeat(db, device, settings=settings, gateway=gateway))
    return results
