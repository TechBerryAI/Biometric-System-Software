"""Worker: process_device_commands task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domains.devices.models.device_command import DeviceCommandStatus
from app.workers.tasks import process_device_commands
from tests.factories import make_device_command


@pytest.mark.testid("BE-WRK-CMD-001")
def test_process_device_commands_drains_claimed() -> None:
    fake_db = MagicMock()
    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "W"},
        status=DeviceCommandStatus.RUNNING.value,
        idempotency_key="wrk-cmd-1",
    )

    with (
        patch("app.workers.tasks.SessionLocal", return_value=fake_db),
        patch("app.workers.tasks.claim_pending_commands", return_value=[cmd]) as claim,
        patch("app.workers.tasks.process_command") as process,
    ):
        result = process_device_commands.run()

    assert result["processed"] == 1
    claim.assert_called_once()
    process.assert_called_once()
    fake_db.commit.assert_called()
    fake_db.close.assert_called_once()
