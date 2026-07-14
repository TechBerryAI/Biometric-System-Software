"""Worker: Celery beat schedule includes critical command tasks."""

from __future__ import annotations

import pytest

from app.workers.celery_app import celery_app


@pytest.mark.testid("BE-WRK-BEAT-001")
def test_beat_schedule_contains_command_and_stale_recovery() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "process-device-commands" in schedule
    assert schedule["process-device-commands"]["task"] == "app.workers.tasks.process_device_commands"
    assert "recover-stale-commands" in schedule
    assert schedule["recover-stale-commands"]["task"] == "app.workers.tasks.recover_stale_commands"
