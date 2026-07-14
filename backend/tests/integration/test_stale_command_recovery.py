"""Integration: recover stale RUNNING commands with old heartbeat."""

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
    """SessionLocal stand-in that does not close the fixture session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def close(self) -> None:
        return None


@pytest.mark.integration
@pytest.mark.testid("BE-INT-STALE-001")
def test_recover_stale_running_commands(db_session: Session) -> None:
    settings = get_settings()
    stale_age = timedelta(minutes=settings.command_stale_minutes + 5)
    old_hb = datetime.now(ZoneInfo("UTC")) - stale_age

    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBISTALE", "name": "Stale"},
        status=DeviceCommandStatus.RUNNING.value,
        idempotency_key="stale-cmd-1",
    )
    cmd.started_at = old_hb
    cmd.heartbeat_at = old_hb
    cmd.retries = 0
    db_session.add(cmd)
    db_session.commit()

    with patch("app.workers.tasks.SessionLocal", lambda: _SessionProxy(db_session)):
        with patch("app.workers.tasks.settings") as task_settings:
            task_settings.command_stale_minutes = settings.command_stale_minutes
            task_settings.command_max_retries = settings.command_max_retries
            result = recover_stale_commands.run()

    assert result["recovered"] >= 1
    db_session.refresh(cmd)
    assert cmd.status == DeviceCommandStatus.RETRYING.value
    assert cmd.last_error and "stale" in cmd.last_error.lower()
