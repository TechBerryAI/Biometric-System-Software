"""Unit tests: sync skips pyzk when TCP preflight fails."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.testid("BE-UNIT-SYNC-TCP-001")
def test_sync_device_skips_when_tcp_unreachable() -> None:
    from app.domains.devices.services.sync_manager_service import sync_device

    device = MagicMock()
    device.name = "main-entrance"
    device.connectivity_mode = "pull"
    db = MagicMock()
    settings = MagicMock()
    gateway = MagicMock()

    with (
        patch(
            "app.domains.devices.services.sync_manager_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.devices.services.sync_manager_service._preflight_device_tcp",
            return_value=(False, "Device unreachable at 192.168.1.200:4370"),
        ),
        patch("app.domains.devices.services.sync_manager_service.device_session_lock") as lock,
        patch(
            "app.domains.devices.services.sync_manager_service.update_device_health_for_device"
        ) as health,
    ):
        result = sync_device(db, device, settings=settings, gateway=gateway)

    assert result["skipped"] == 1
    assert result["skipped_reason"] == "device_unreachable"
    lock.assert_not_called()
    health.assert_called_once()


@pytest.mark.testid("BE-UNIT-SYNC-TCP-002")
def test_sync_device_push_mode_skips_tcp_preflight() -> None:
    from app.domains.devices.services.sync_manager_service import sync_device

    device = MagicMock()
    device.name = "push-gate"
    device.connectivity_mode = "push"
    db = MagicMock()
    settings = MagicMock()
    gateway = MagicMock()

    with (
        patch(
            "app.domains.devices.services.sync_manager_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch("app.domains.devices.services.sync_manager_service._preflight_device_tcp") as preflight,
        patch("app.domains.devices.services.sync_manager_service.device_session_lock") as lock,
        patch("app.domains.devices.services.sync_manager_service.run_user_sync", return_value=(0, 0)),
        patch("app.domains.devices.services.sync_manager_service.run_device_sync_detailed") as attendance_sync,
        patch("app.domains.devices.services.sync_manager_service.get_or_create_sync_state"),
        patch("app.domains.devices.services.sync_manager_service.update_device_health_for_device"),
    ):
        attendance_sync.return_value = MagicMock(
            fetched=1,
            inserted=1,
            placeholders=0,
            skipped_corrected_punches=0,
            punches_missing_after_insert=0,
            skipped_reason=None,
        )
        result = sync_device(db, device, settings=settings, gateway=gateway)

    preflight.assert_not_called()
    lock.assert_called_once()
    assert "skipped" not in result
    assert result["inserted"] == 1
