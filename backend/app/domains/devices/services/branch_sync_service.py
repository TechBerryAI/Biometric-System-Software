"""Branch-level device sync scheduling and coordination."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.services.heartbeat_service import probe_device_heartbeat
from app.domains.devices.services.sync_manager_service import sync_device

logger = logging.getLogger(__name__)


def group_devices_by_branch(devices: list[Device]) -> dict[str | None, list[Device]]:
    grouped: dict[str | None, list[Device]] = defaultdict(list)
    for device in devices:
        grouped[device.branch_id].append(device)
    return dict(grouped)


def stagger_order(devices: list[Device], *, seed: str = "branch-sync") -> list[Device]:
    """Deterministic stagger order to spread load across devices."""

    def sort_key(device: Device) -> str:
        digest = hashlib.sha256(f"{seed}:{device.name}".encode()).hexdigest()
        return digest

    return sorted(devices, key=sort_key)


def sync_branch(
    db: Session,
    branch_id: str | None,
    *,
    full_resync: bool = True,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> list[dict[str, int | str]]:
    """Sync all pull devices in a branch with staggered ordering."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    devices = gateway.list_pull_devices(db, branch_id=branch_id)
    ordered = stagger_order(devices, seed=branch_id or "default")
    results: list[dict[str, int | str]] = []
    for device in ordered:
        try:
            counts = sync_device(db, device, full_resync=full_resync, settings=settings, gateway=gateway)
            results.append({"device_id": device.name, "branch_id": branch_id or "", **counts})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Branch sync failed for %s: %s", device.name, exc)
            results.append({"device_id": device.name, "branch_id": branch_id or "", "error": str(exc)})
    return results


def probe_branch(
    db: Session,
    branch_id: str | None,
    *,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> list[dict[str, object]]:
    """Probe all devices in a branch."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    devices = gateway.list_pull_devices(db, branch_id=branch_id)
    return [probe_device_heartbeat(db, device, settings=settings, gateway=gateway) for device in devices]
