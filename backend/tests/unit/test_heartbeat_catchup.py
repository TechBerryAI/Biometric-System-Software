"""Unit tests for OFFLINE→ONLINE catch-up sync enqueue and probe soft-fail."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.devices.services.heartbeat_service import probe_device_heartbeat
from app.shared.device_exceptions import DeviceLockContentionError
from tests.factories import make_device


@pytest.mark.testid("BE-UNIT-HB-CATCHUP-001")
def test_probe_enqueues_catchup_when_device_returns_online(db_session: Session) -> None:
    settings = get_settings()
    device = make_device(name="gate-catchup", health_status="OFFLINE")
    db_session.add(device)
    db_session.commit()

    gateway = MagicMock()
    gateway.probe_device.return_value = (True, "connected")
    connector = MagicMock()
    connector.detect_firmware_fingerprint.return_value = {"firmware_version": "unknown"}
    gateway.get_connector.return_value = connector

    with (
        patch.object(settings, "device_auto_sync_enabled", True),
        patch("app.domains.devices.services.heartbeat_service.device_session_lock") as lock,
        patch("app.domains.devices.services.heartbeat_service._enqueue_catchup_sync") as enqueue,
    ):
        lock.return_value.__enter__ = MagicMock(return_value=None)
        lock.return_value.__exit__ = MagicMock(return_value=False)
        result = probe_device_heartbeat(db_session, device, settings=settings, gateway=gateway)

    assert result["online"] is True
    assert result["catchup_sync_enqueued"] is True
    enqueue.assert_called_once_with(device_id="gate-catchup")


@pytest.mark.testid("BE-UNIT-HB-BUSY-001")
def test_probe_skips_when_device_lock_busy(db_session: Session) -> None:
    settings = get_settings()
    device = make_device(name="gate-busy", health_status="ONLINE")
    db_session.add(device)
    db_session.commit()

    gateway = MagicMock()
    with patch(
        "app.domains.devices.services.heartbeat_service.device_session_lock",
        side_effect=DeviceLockContentionError("busy"),
    ):
        result = probe_device_heartbeat(db_session, device, settings=settings, gateway=gateway)

    assert result["skipped_reason"] == "device_lock_busy"
    assert result["online"] is True
    assert device.health_status == "ONLINE"
    gateway.probe_device.assert_not_called()


@pytest.mark.testid("BE-UNIT-HB-GRACE-001")
def test_probe_soft_fails_within_recent_sync_grace(db_session: Session) -> None:
    settings = get_settings()
    device = make_device(name="gate-grace", health_status="ONLINE")
    device.last_seen = datetime.now(ZoneInfo("UTC")) - timedelta(seconds=30)
    db_session.add(device)
    db_session.add(
        DeviceSyncState(
            device_id="gate-grace",
            last_attendance_sync_at=datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    gateway = MagicMock()
    gateway.probe_device.return_value = (False, "timeout")

    with patch("app.domains.devices.services.heartbeat_service.device_session_lock") as lock:
        lock.return_value.__enter__ = MagicMock(return_value=None)
        lock.return_value.__exit__ = MagicMock(return_value=False)
        result = probe_device_heartbeat(db_session, device, settings=settings, gateway=gateway)

    assert result["skipped_reason"] == "recent_connectivity_grace"
    assert device.health_status == "ONLINE"
