"""Per-device connection parameters for fleet orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.app_timezone import DEFAULT_TIMEZONE
from app.core.config import Settings
from app.domains.devices.models.device import Device


@dataclass(frozen=True, slots=True)
class DeviceConnectionConfig:
    """Connection parameters for a single biometric terminal."""

    device_id: str
    ip_address: str
    port: int
    password: int = 0
    timeout_seconds: int = 30
    force_udp: bool = False
    omit_ping: bool = False
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def from_settings(cls, settings: Settings) -> DeviceConnectionConfig:
        return cls(
            device_id=settings.zk_device_id,
            ip_address=settings.zk_device_ip,
            port=settings.zk_device_port,
            password=settings.zk_device_password,
            timeout_seconds=settings.zk_device_timeout_seconds,
            force_udp=settings.zk_force_udp,
            omit_ping=settings.zk_omit_ping,
            timezone=settings.resolved_timezone(),
        )

    @classmethod
    def from_device(cls, device: Device, settings: Settings | None = None) -> DeviceConnectionConfig:
        from app.core.config import get_settings

        cfg = settings or get_settings()
        device_password = cfg.zk_device_password
        if device.capabilities and isinstance(device.capabilities, dict):
            raw_password = device.capabilities.get("device_password")
            if raw_password is not None:
                try:
                    device_password = int(raw_password)
                except (TypeError, ValueError):
                    pass
        return cls(
            device_id=device.name,
            ip_address=device.ip_address,
            port=device.port,
            password=device_password,
            timeout_seconds=cfg.zk_device_timeout_seconds,
            force_udp=cfg.zk_force_udp,
            omit_ping=cfg.zk_omit_ping,
            timezone=device.timezone or cfg.resolved_timezone(),
        )
