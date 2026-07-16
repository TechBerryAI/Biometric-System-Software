"""Worker: sync_attendance_from_device task body."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import sync_attendance_from_device


@pytest.mark.testid("BE-WRK-SYNC-001")
def test_sync_attendance_from_device_runs_with_patches() -> None:
    fake_db = MagicMock()

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.ensure_default_device") as ensure_device,
        patch("app.workers.tasks.sync_branch") as sync_branch,
    ):
        settings.device_auto_sync_enabled = True
        sync_branch.return_value = [
            {"device_id": "main-entrance", "inserted": 4, "fetched": 10, "users_fetched": 3}
        ]
        result = sync_attendance_from_device.run()

    assert result["devices"] == 1
    assert result["total_inserted"] == 4
    ensure_device.assert_called_once()
    sync_branch.assert_called_once()
    assert fake_db.commit.call_count >= 1
    fake_db.close.assert_called_once()
