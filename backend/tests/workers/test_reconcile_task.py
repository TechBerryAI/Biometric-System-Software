"""Worker: reconcile_devices task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import reconcile_devices


@pytest.mark.testid("BE-WRK-REC-001")
def test_reconcile_devices_runs_with_patches() -> None:
    fake_db = MagicMock()

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.ensure_default_device"),
        patch(
            "app.workers.tasks.reconcile_all_devices",
            return_value=[{"device_id": "main-entrance", "missing_on_device": 1, "missing_mapping": 2}],
        ) as reconcile,
    ):
        settings.device_auto_sync_enabled = True
        result = reconcile_devices.run()

    assert result["total_drift"] == 3
    assert result["devices"] == 1
    reconcile.assert_called_once()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
