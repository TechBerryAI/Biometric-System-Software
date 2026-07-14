"""Worker: reconcile_devices task."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.workers.tasks import reconcile_devices


@pytest.mark.testid("BE-WRK-REC-001")
def test_reconcile_devices_runs_with_patches() -> None:
    fake_db = MagicMock()

    @contextmanager
    def _lock(*_a, **_k):
        yield

    with (
        patch("app.workers.tasks.settings") as settings,
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.device_session_lock", _lock),
        patch(
            "app.workers.tasks.reconcile_device_mappings",
            return_value={"missing_on_device": 1, "missing_mapping": 2},
        ) as reconcile,
    ):
        settings.device_auto_sync_enabled = True
        settings.zk_device_id = "main-entrance"
        result = reconcile_devices.run()

    assert result["missing_on_device"] == 1
    assert result["missing_mapping"] == 2
    reconcile.assert_called_once()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
