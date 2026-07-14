"""Worker: sync_attendance_from_device task body."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import sync_attendance_from_device


@pytest.mark.testid("BE-WRK-SYNC-001")
def test_sync_attendance_from_device_runs_with_patches() -> None:
    fake_db = MagicMock()

    @contextmanager
    def _lock(*_a, **_k):
        yield

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.device_session_lock", _lock),
        patch("app.workers.tasks.run_user_sync", return_value=(3, 1)) as user_sync,
        patch("app.workers.tasks.run_device_sync", return_value=(10, 4, 0)) as device_sync,
        patch("app.workers.tasks.update_device_health") as health,
    ):
        settings.device_auto_sync_enabled = True
        settings.zk_device_id = "main-entrance"
        result = sync_attendance_from_device.run()

    assert result["fetched"] == 10
    assert result["inserted"] == 4
    assert result["users_fetched"] == 3
    user_sync.assert_called_once()
    device_sync.assert_called_once()
    health.assert_called()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
