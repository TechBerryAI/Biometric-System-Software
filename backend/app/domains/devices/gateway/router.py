"""Connection pool and routing for fleet device access."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.config import Settings, get_settings
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.gateway.base import DeviceConnector, PullConnector
from app.domains.devices.gateway.push_connector import PushConnector
from app.domains.devices.models.device import Device

logger = logging.getLogger(__name__)


class DeviceGateway:
    """Unified gateway for pull-based device fleet access with pooled connectors."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._connectors: dict[str, PullConnector] = {}
        self._last_used: dict[str, float] = {}
        self._lock = threading.Lock()
        self._sync_sem = threading.Semaphore(self._settings.gateway_sync_semaphore)
        self._breaker = CircuitBreaker(
            failure_threshold=5,
            reset_seconds=60,
            name="device_gateway",
        )

    def connection_for_device(self, device: Device) -> DeviceConnectionConfig:
        return DeviceConnectionConfig.from_device(device, self._settings)

    def _evict_idle_locked(self) -> None:
        """Evict idle connectors and enforce max pool size (caller holds lock)."""
        now = time.monotonic()
        idle_ttl = self._settings.gateway_idle_ttl_seconds
        max_connectors = self._settings.gateway_max_connectors
        stale = [
            device_id
            for device_id, last in self._last_used.items()
            if now - last > idle_ttl
        ]
        for device_id in stale:
            self._connectors.pop(device_id, None)
            self._last_used.pop(device_id, None)
        while len(self._connectors) > max_connectors:
            # Evict least-recently used.
            victim = min(self._last_used, key=self._last_used.get)  # type: ignore[arg-type]
            self._connectors.pop(victim, None)
            self._last_used.pop(victim, None)

    def get_connector(self, device: Device) -> PullConnector:
        device_id = device.name
        with self._lock:
            self._evict_idle_locked()
            existing = self._connectors.get(device_id)
            if existing is not None:
                if (
                    existing.connection.ip_address == device.ip_address
                    and existing.connection.port == device.port
                ):
                    self._last_used[device_id] = time.monotonic()
                    return existing
            # Make room before inserting a new connector.
            while len(self._connectors) >= self._settings.gateway_max_connectors:
                if not self._last_used:
                    break
                victim = min(self._last_used, key=self._last_used.get)  # type: ignore[arg-type]
                self._connectors.pop(victim, None)
                self._last_used.pop(victim, None)
            connector = PullConnector(self.connection_for_device(device))
            self._connectors[device_id] = connector
            self._last_used[device_id] = time.monotonic()
            return connector

    def get_connector_by_id(self, db: Session, device_id: str) -> PullConnector | None:
        device = db.execute(select(Device).where(Device.name == device_id, Device.active.is_(True))).scalar_one_or_none()
        if device is None:
            return None
        return self.get_connector(device)

    def list_active_devices(self, db: Session, *, branch_id: str | None = None) -> list[Device]:
        stmt = select(Device).where(Device.active.is_(True))
        if branch_id is not None:
            stmt = stmt.where(Device.branch_id == branch_id)
        return list(db.execute(stmt.order_by(Device.id)).scalars().all())

    def list_pull_devices(self, db: Session, *, branch_id: str | None = None) -> list[Device]:
        devices = self.list_active_devices(db, branch_id=branch_id)
        return [d for d in devices if d.connectivity_mode in {"pull", "both"}]

    @contextmanager
    def session(self, device: Device) -> Iterator[PullConnector]:
        acquired = self._sync_sem.acquire(timeout=self._settings.zk_device_timeout_seconds)
        if not acquired:
            raise TimeoutError(f"Gateway sync semaphore exhausted for device={device.name}")
        try:
            connector = self.get_connector(device)
            yield connector
        finally:
            self._sync_sem.release()

    def get_push_connector(self, device: Device) -> PushConnector:
        return PushConnector(self.connection_for_device(device), device.offline_buffer)

    def resolve_connector(self, device: Device) -> DeviceConnector:
        if device.connectivity_mode == "push":
            return self.get_push_connector(device)
        return self.get_connector(device)

    def probe_device(self, device: Device) -> tuple[bool, str]:
        if not self._breaker.can_execute():
            raise CircuitOpenError(f"Device gateway circuit open until {self._breaker.opened_until()}")
        try:
            result = self.resolve_connector(device).check_connection()
            if result[0]:
                self._breaker.record_success()
            else:
                self._breaker.record_failure()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            self._breaker.record_failure()
            raise

    def invalidate(self, device_id: str) -> None:
        with self._lock:
            self._connectors.pop(device_id, None)
            self._last_used.pop(device_id, None)

    def pool_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connectors": len(self._connectors),
                "max_connectors": self._settings.gateway_max_connectors,
                "sync_semaphore": self._settings.gateway_sync_semaphore,
            }

    def shutdown(self) -> None:
        with self._lock:
            self._connectors.clear()
            self._last_used.clear()


_gateway: DeviceGateway | None = None
_gateway_lock = threading.Lock()


def get_device_gateway(settings: Settings | None = None) -> DeviceGateway:
    global _gateway
    with _gateway_lock:
        if _gateway is None:
            _gateway = DeviceGateway(settings=settings)
        return _gateway


def reset_device_gateway() -> None:
    """Reset singleton gateway (tests)."""
    global _gateway
    with _gateway_lock:
        if _gateway is not None:
            _gateway.shutdown()
        _gateway = None
