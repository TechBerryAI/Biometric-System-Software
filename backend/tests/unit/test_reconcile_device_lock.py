"""Unit tests: reconcile must not open ZK while another task holds the device lock."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.shared.device_exceptions import DeviceLockContentionError


@pytest.mark.testid("BE-UNIT-RECON-LOCK-001")
def test_reconcile_skips_when_device_lock_busy() -> None:
    from app.domains.devices.services.device_registry_service import reconcile_device_mappings

    device = MagicMock()
    device.name = "main-entrance"
    device.tenant_id = None
    db = MagicMock()

    @contextmanager
    def _busy_lock(*_a, **_k):
        raise DeviceLockContentionError("busy")
        yield  # pragma: no cover

    with (
        patch(
            "app.domains.devices.services.device_registry_service.device_session_lock",
            side_effect=_busy_lock,
        ),
        patch("app.domains.devices.services.device_registry_service.DeviceService") as svc,
    ):
        svc.return_value.probe_tcp_connection.return_value = (True, "tcp_connected")
        result = reconcile_device_mappings(db, device=device, settings=MagicMock())

    assert result["skipped"] == 1
    assert result["skipped_reason"] == "device_lock_busy"
    svc.return_value.fetch_users.assert_not_called()


@pytest.mark.testid("BE-UNIT-RECON-TCP-001")
def test_reconcile_skips_when_tcp_unreachable() -> None:
    from app.domains.devices.services.device_registry_service import reconcile_device_mappings

    device = MagicMock()
    device.name = "main-entrance"
    device.tenant_id = None
    db = MagicMock()

    with (
        patch(
            "app.domains.devices.services.device_registry_service.DeviceService"
        ) as svc_cls,
        patch(
            "app.domains.devices.services.device_registry_service.device_session_lock",
        ) as lock,
    ):
        svc_cls.return_value.probe_tcp_connection.return_value = (
            False,
            "Device unreachable at 192.168.1.200:4370",
        )
        result = reconcile_device_mappings(db, device=device, settings=MagicMock())

    assert result["skipped"] == 1
    assert result["skipped_reason"] == "device_unreachable"
    lock.assert_not_called()
