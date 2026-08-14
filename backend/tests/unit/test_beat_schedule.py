"""Unit tests for OffsetInterval beat schedule helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.workers.beat_schedule import OffsetInterval


@pytest.mark.testid("BE-UNIT-BEAT-001")
def test_offset_interval_not_due_during_initial_delay() -> None:
    sched = OffsetInterval(timedelta(seconds=60), initial_delay=30)
    overdue = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch("app.workers.beat_schedule.time.monotonic", return_value=sched._boot + 5):
        due = sched.is_due(overdue)
    assert due.is_due is False
    assert due.next <= 30


@pytest.mark.testid("BE-UNIT-BEAT-002")
def test_offset_interval_due_after_initial_delay_when_overdue() -> None:
    sched = OffsetInterval(timedelta(seconds=60), initial_delay=10)
    overdue = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch("app.workers.beat_schedule.time.monotonic", return_value=sched._boot + 15):
        due = sched.is_due(overdue)
    assert due.is_due is True
