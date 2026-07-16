"""Worker: probe_device_connectivity task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import probe_device_connectivity


@pytest.mark.testid("BE-WRK-PROBE-001")
def test_probe_device_connectivity_updates_health() -> None:
    fake_db = MagicMock()

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.ensure_default_device"),
        patch("app.workers.tasks.probe_all_devices") as probe_all,
    ):
        settings.device_auto_sync_enabled = True
        probe_all.return_value = [{"device_id": "main-entrance", "online": True, "detail": "tcp_ok"}]
        result = probe_device_connectivity.run()

    assert result["online"] == 1
    assert result["probed"] == 1
    probe_all.assert_called_once()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
