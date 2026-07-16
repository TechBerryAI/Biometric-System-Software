"""Central device fleet orchestration."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.services.branch_sync_service import probe_branch, sync_branch
from app.domains.devices.services.device_command_service import enqueue_device_command
from app.domains.devices.services.device_config_service import get_device_config, update_device_config
from app.domains.devices.services.device_registry_service import (
    create_device,
    deactivate_device,
    get_device_by_name,
    list_devices,
    update_device,
)
from app.domains.devices.services.heartbeat_service import probe_all_devices, probe_device_heartbeat
from app.domains.devices.services.sync_manager_service import sync_device, sync_all_pull_devices

logger = logging.getLogger(__name__)


class DeviceManagerService:
    """Orchestrates device registry, gateway, sync, and remote commands."""

    def __init__(self, db: Session, settings: Settings | None = None, gateway: DeviceGateway | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._gateway = gateway or get_device_gateway(self._settings)

    def list_fleet(self, *, branch_id: str | None = None, active_only: bool = True) -> list[Device]:
        return list_devices(self._db, branch_id=branch_id, active_only=active_only)

    def get_device(self, device_name: str) -> Device | None:
        return get_device_by_name(self._db, device_name)

    def register_device(self, **kwargs: Any) -> Device:
        device = create_device(self._db, settings=self._settings, **kwargs)
        self._db.flush()
        return device

    def update_device_record(self, device: Device, **kwargs: Any) -> Device:
        updated = update_device(self._db, device, **kwargs)
        self._gateway.invalidate(device.name)
        return updated

    def deactivate(self, device: Device, *, reason: str | None = None) -> Device:
        result = deactivate_device(self._db, device, reason=reason)
        self._gateway.invalidate(device.name)
        return result

    def get_health(self, device: Device) -> dict[str, Any]:
        return {
            "device_id": device.name,
            "health_status": device.health_status,
            "mode": device.mode,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "firmware_version": device.firmware_version,
            "connectivity_mode": device.connectivity_mode,
            "branch_id": device.branch_id,
        }

    def probe_health(self, device: Device) -> dict[str, object]:
        return probe_device_heartbeat(self._db, device, settings=self._settings, gateway=self._gateway)

    def probe_fleet(self, *, branch_id: str | None = None) -> list[dict[str, object]]:
        if branch_id is not None:
            return probe_branch(self._db, branch_id, settings=self._settings, gateway=self._gateway)
        return probe_all_devices(self._db, settings=self._settings, gateway=self._gateway)

    def sync_device(self, device: Device, *, full_resync: bool = True) -> dict[str, int]:
        return sync_device(self._db, device, full_resync=full_resync, settings=self._settings, gateway=self._gateway)

    def sync_fleet(self, *, branch_id: str | None = None, full_resync: bool = True) -> list[dict[str, int | str]]:
        if branch_id is not None:
            return sync_branch(self._db, branch_id, full_resync=full_resync, settings=self._settings, gateway=self._gateway)
        return sync_all_pull_devices(self._db, branch_id=branch_id, settings=self._settings, gateway=self._gateway)

    def get_config(self, device: Device) -> dict[str, Any]:
        return get_device_config(device)

    def update_config(
        self,
        device: Device,
        config: dict[str, Any],
        *,
        initiated_by: str | None = None,
        apply_to_device: bool = True,
    ) -> Device:
        return update_device_config(
            self._db,
            device,
            config,
            initiated_by=initiated_by,
            apply_to_device=apply_to_device,
        )

    def enqueue_command(
        self,
        device: Device,
        command_type: str,
        payload: dict[str, Any],
        *,
        initiated_by: str | None = None,
        initiated_from: str = "device_manager",
    ) -> Any:
        return enqueue_device_command(
            self._db,
            device_id=device.name,
            command_type=command_type,
            payload=payload,
            correlation_id=None,
            created_by=initiated_by,
            initiated_from=initiated_from,
        )
