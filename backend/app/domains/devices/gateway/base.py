"""Abstract device gateway connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser


class DeviceConnector(ABC):
    """Transport-specific connector for a single biometric terminal."""

    @property
    @abstractmethod
    def connection(self) -> DeviceConnectionConfig:
        """Connection parameters for this connector."""

    @abstractmethod
    def check_connection(self) -> tuple[bool, str]:
        """Probe device reachability."""

    @abstractmethod
    def fetch_users(self) -> list[DeviceUser]:
        """Pull user metadata from the device."""

    @abstractmethod
    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        """Pull attendance records from the device."""

    def detect_firmware_fingerprint(self) -> dict[str, Any]:
        """Best-effort firmware fingerprint."""
        return {}


class PullConnector(DeviceConnector):
    """pyzk pull connector backed by DeviceService."""

    def __init__(self, connection: DeviceConnectionConfig) -> None:
        self._connection = connection
        self._service = DeviceService(connection=connection)

    @property
    def connection(self) -> DeviceConnectionConfig:
        return self._connection

    @property
    def service(self) -> DeviceService:
        return self._service

    def check_connection(self) -> tuple[bool, str]:
        return self._service.check_connection()

    def fetch_users(self) -> list[DeviceUser]:
        return self._service.fetch_users()

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        return self._service.fetch_attendance()

    def detect_firmware_fingerprint(self) -> dict[str, Any]:
        return self._service.detect_firmware_fingerprint()
