"""Simulate a 1000-device fleet (pool limits + semaphore)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.domains.devices.gateway.router import DeviceGateway, reset_device_gateway


def _fake_device(idx: int) -> MagicMock:
    device = MagicMock()
    device.name = f"device-{idx:04d}"
    device.ip_address = f"10.{(idx // 65536) % 256}.{(idx // 256) % 256}.{idx % 256}"
    device.port = 4370
    device.connectivity_mode = "pull"
    device.branch_id = f"branch-{idx % 50}"
    device.offline_buffer = None
    device.active = True
    device.timezone = "UTC"
    return device


@pytest.mark.device_sim
@pytest.mark.slow
@pytest.mark.testid("BE-SIM-1000-001")
def test_gateway_handles_1000_device_churn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_MAX_CONNECTORS", "200")
    monkeypatch.setenv("GATEWAY_SYNC_SEMAPHORE", "16")
    get_settings.cache_clear()
    reset_device_gateway()

    settings = get_settings()
    gateway = DeviceGateway(settings=settings)

    class _FakePull:
        def __init__(self, connection) -> None:
            self.connection = connection

        def check_connection(self) -> tuple[bool, str]:
            return True, "ok"

    monkeypatch.setattr(
        "app.domains.devices.gateway.router.PullConnector",
        lambda connection: _FakePull(connection),
    )
    monkeypatch.setattr(
        "app.domains.devices.gateway.router.DeviceConnectionConfig.from_device",
        lambda device, settings: MagicMock(ip_address=device.ip_address, port=device.port),
    )

    devices = [_fake_device(i) for i in range(1000)]
    for device in devices:
        gateway.get_connector(device)

    stats = gateway.pool_stats()
    assert stats["connectors"] <= 200
    assert stats["sync_semaphore"] == 16

    # Semaphore context managers should not deadlock for a burst of sessions.
    acquired = 0
    for device in devices[:32]:
        with gateway.session(device):
            acquired += 1
    assert acquired == 32

    reset_device_gateway()
    get_settings.cache_clear()


@pytest.mark.device_sim
@pytest.mark.testid("BE-SIM-1000-002")
def test_pool_stats_stable_after_invalidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_MAX_CONNECTORS", "100")
    get_settings.cache_clear()
    reset_device_gateway()
    gateway = DeviceGateway(settings=get_settings())

    class _FakePull:
        def __init__(self, connection) -> None:
            self.connection = connection

    monkeypatch.setattr(
        "app.domains.devices.gateway.router.PullConnector",
        lambda connection: _FakePull(connection),
    )
    monkeypatch.setattr(
        "app.domains.devices.gateway.router.DeviceConnectionConfig.from_device",
        lambda device, settings: MagicMock(ip_address=device.ip_address, port=device.port),
    )

    for i in range(100):
        gateway.get_connector(_fake_device(i))
    gateway.invalidate("device-0000")
    assert gateway.pool_stats()["connectors"] == 99
    reset_device_gateway()
    get_settings.cache_clear()
