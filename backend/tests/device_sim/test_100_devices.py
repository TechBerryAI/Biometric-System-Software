"""Simulate a 100-device fleet against the in-memory gateway pool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.domains.devices.gateway.router import DeviceGateway, reset_device_gateway


def _fake_device(idx: int) -> MagicMock:
    device = MagicMock()
    device.name = f"device-{idx:03d}"
    device.ip_address = f"10.0.{idx // 250}.{idx % 250}"
    device.port = 4370
    device.connectivity_mode = "pull"
    device.branch_id = f"branch-{idx % 10}"
    device.offline_buffer = None
    device.active = True
    device.timezone = "UTC"
    return device


@pytest.mark.device_sim
@pytest.mark.testid("BE-SIM-100-001")
def test_gateway_pools_100_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_MAX_CONNECTORS", "120")
    monkeypatch.setenv("GATEWAY_IDLE_TTL_SECONDS", "600")
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

    devices = [_fake_device(i) for i in range(100)]
    for device in devices:
        connector = gateway.get_connector(device)
        assert connector is not None

    stats = gateway.pool_stats()
    assert stats["connectors"] == 100
    assert stats["max_connectors"] >= 100

    # Re-fetch should reuse pooled connectors.
    first = gateway.get_connector(devices[0])
    second = gateway.get_connector(devices[0])
    assert first is second

    reset_device_gateway()
    get_settings.cache_clear()


@pytest.mark.device_sim
@pytest.mark.testid("BE-SIM-100-002")
def test_gateway_evicts_when_over_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_MAX_CONNECTORS", "50")
    get_settings.cache_clear()
    reset_device_gateway()
    settings = get_settings()
    gateway = DeviceGateway(settings=settings)

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

    for i in range(80):
        gateway.get_connector(_fake_device(i))

    assert gateway.pool_stats()["connectors"] <= 50
    reset_device_gateway()
    get_settings.cache_clear()
