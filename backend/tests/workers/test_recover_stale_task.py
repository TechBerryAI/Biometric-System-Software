"""Worker: recover_stale_commands task."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.devices.models.device_command import DeviceCommandStatus
from app.workers.tasks import recover_stale_commands
from tests.factories import make_device_command


class _SessionProxy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def close(self) -> None:
        return None


@pytest.mark.testid("BE-WRK-STALE-001")
def test_recover_stale_commands_task(db_session: Session) -> None:
    settings = get_settings()
    old = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=settings.command_stale_minutes + 2)
    cmd = make_device_command(
        command_type="DELETE_USER",
        payload={"user_id": "TBI001"},
        status=DeviceCommandStatus.RUNNING.value,
        idempotency_key="wrk-stale-1",
    )
    cmd.started_at = old
    cmd.heartbeat_at = old
    cmd.retries = 0
    db_session.add(cmd)
    db_session.commit()

    with (
        patch("app.workers.tasks.SessionLocal", lambda: _SessionProxy(db_session)),
        patch("app.workers.tasks.settings") as task_settings,
    ):
        task_settings.command_stale_minutes = settings.command_stale_minutes
        task_settings.command_max_retries = settings.command_max_retries
        result = recover_stale_commands.run()

    assert result["recovered"] >= 1
    db_session.refresh(cmd)
    assert cmd.status == DeviceCommandStatus.RETRYING.value
