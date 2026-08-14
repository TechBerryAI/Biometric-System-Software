"""Runtime device TCP and errors must use Settings/DB IP, not env default."""

from __future__ import annotations

import errno
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.models.device_command import DeviceCommandStatus
from app.domains.devices.services.device_command_service import (
    _device_service_for_command,
    process_command,
)
from app.domains.devices.services.device_registry_service import device_service_for
from app.domains.devices.services.device_service import DeviceService, format_device_connection_error
from tests.factories import make_control_state, make_device, make_device_command

SAVED_IP = "192.168.1.85"
SAVED_PORT = 4370


def _saved_connection() -> DeviceConnectionConfig:
    return DeviceConnectionConfig(
        device_id="main-entrance",
        ip_address=SAVED_IP,
        port=SAVED_PORT,
    )


@pytest.mark.testid("BE-UNIT-DEVIP-001")
def test_format_connection_error_uses_connection_ip_not_env() -> None:
    settings = get_settings()
    exc = OSError(errno.EPIPE, "Broken pipe")
    detail = format_device_connection_error(exc, settings=settings, connection=_saved_connection())
    assert f"{SAVED_IP}:{SAVED_PORT}" in detail
    assert settings.zk_device_ip not in detail or settings.zk_device_ip == SAVED_IP


@pytest.mark.testid("BE-UNIT-DEVIP-002")
def test_check_connection_handshake_error_uses_service_connection() -> None:
    settings = get_settings()
    service = DeviceService(settings=settings, connection=_saved_connection())
    service.probe_tcp_connection = lambda: (True, "tcp_connected")  # type: ignore[method-assign]
    service._adapter.run = MagicMock(side_effect=OSError(errno.EPIPE, "Broken pipe"))
    ok, detail = service.check_connection()
    assert ok is False
    assert f"{SAVED_IP}:{SAVED_PORT}" in detail
    if settings.zk_device_ip != SAVED_IP:
        assert settings.zk_device_ip not in detail


@pytest.mark.testid("BE-UNIT-DEVIP-003")
def test_device_service_for_uses_db_ip_not_env(db_session: Session) -> None:
    settings = get_settings()
    db_session.add(
        make_device(
            name=settings.zk_device_id,
            ip_address=SAVED_IP,
            port=SAVED_PORT,
            connectivity_mode="both",
        )
    )
    db_session.commit()

    service = device_service_for(db_session, settings=settings)
    assert service.connection.ip_address == SAVED_IP
    assert service.connection.port == SAVED_PORT
    if settings.zk_device_ip != SAVED_IP:
        assert service.connection.ip_address != settings.zk_device_ip


@pytest.mark.testid("BE-UNIT-DEVIP-004")
def test_device_service_for_named_device_uses_that_row(db_session: Session) -> None:
    db_session.add(make_device(name="lobby", ip_address="10.9.8.7", port=5000))
    db_session.commit()
    service = device_service_for(db_session, device_name="lobby")
    assert service.connection.ip_address == "10.9.8.7"
    assert service.connection.port == 5000


@pytest.mark.testid("BE-UNIT-DEVIP-005")
def test_command_service_uses_db_ip(db_session: Session) -> None:
    settings = get_settings()
    db_session.add(make_device(name="cmd-dev", ip_address="10.1.2.3", port=4370))
    cmd = make_device_command(device_id="cmd-dev")
    db_session.add(cmd)
    db_session.commit()

    service = _device_service_for_command(db_session, cmd, settings)
    assert service.connection.ip_address == "10.1.2.3"


@pytest.mark.testid("BE-UNIT-DEVIP-006")
def test_process_command_fails_when_device_row_missing(db_session: Session) -> None:
    settings = get_settings()
    db_session.add(make_control_state())
    cmd = make_device_command(device_id="missing-device")
    db_session.add(cmd)
    db_session.commit()

    fake_lock = MagicMock()
    with (
        patch(
            "app.domains.devices.services.device_command_service._acquire_lock",
            return_value=(None, fake_lock, "lock-key"),
        ),
        patch("app.domains.devices.services.device_command_service._LockHeartbeat") as hb_cls,
    ):
        hb_cls.return_value = MagicMock()
        process_command(db_session, cmd, settings=settings, worker_id="test-worker")

    assert cmd.status == DeviceCommandStatus.FAILED.value
    assert "not found" in (cmd.last_error or "")
    fake_lock.release.assert_called()
    if settings.zk_device_ip != SAVED_IP:
        assert settings.zk_device_ip not in (cmd.last_error or "")
