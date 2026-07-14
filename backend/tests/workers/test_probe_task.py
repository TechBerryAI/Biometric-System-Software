"""Worker: probe_device_connectivity task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import probe_device_connectivity


@pytest.mark.testid("BE-WRK-PROBE-001")
def test_probe_device_connectivity_updates_health() -> None:
    fake_db = MagicMock()
    device = MagicMock()
    device.check_connection.return_value = (True, "tcp_ok")

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.DeviceService", return_value=device),
        patch("app.workers.tasks.update_device_health") as health,
    ):
        settings.device_auto_sync_enabled = True
        result = probe_device_connectivity.run()

    assert result["online"] is True
    assert result["detail"] == "tcp_ok"
    health.assert_called()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
