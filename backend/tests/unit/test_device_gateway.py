"""Unit tests for device gateway and connection config."""

from __future__ import annotations

from app.core.config import get_settings
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.gateway.router import DeviceGateway, reset_device_gateway
from tests.factories import make_device


def test_connection_config_from_settings():
    settings = get_settings()
    conn = DeviceConnectionConfig.from_settings(settings)
    assert conn.device_id == settings.zk_device_id
    assert conn.ip_address == settings.zk_device_ip


def test_connection_config_from_device():
    device = make_device(name="gw-test", ip_address="10.0.0.5", port=4370)
    conn = DeviceConnectionConfig.from_device(device)
    assert conn.device_id == "gw-test"
    assert conn.ip_address == "10.0.0.5"


def test_gateway_lists_pull_devices(db_session):
    reset_device_gateway()
    db_session.add(make_device(name="pull-1", connectivity_mode="pull"))
    db_session.add(make_device(name="push-1", connectivity_mode="push"))
    db_session.commit()
    gateway = DeviceGateway()
    pull_devices = gateway.list_pull_devices(db_session)
    names = {d.name for d in pull_devices}
    assert "pull-1" in names
    assert "push-1" not in names
