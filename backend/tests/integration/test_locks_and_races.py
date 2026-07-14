"""Integration: employee-day lock serializes concurrent work."""

from __future__ import annotations

import threading
import time
from datetime import date
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.domains.attendance.services.attendance_lock_service import employee_day_lock


@pytest.mark.integration
@pytest.mark.testid("BE-INT-LOCK-001")
def test_employee_day_lock_serializes_concurrent_access() -> None:
    settings = get_settings()
    day = date(2026, 7, 14)
    order: list[str] = []
    barrier = threading.Barrier(2)

    def _worker(label: str) -> None:
        barrier.wait(timeout=5)
        with employee_day_lock(42, day, settings, blocking_timeout=5):
            order.append(f"{label}-enter")
            time.sleep(0.08)
            order.append(f"{label}-exit")

    # Force local fallback so Redis flakiness does not hide lock behavior
    with patch(
        "app.domains.attendance.services.attendance_lock_service.Redis.from_url",
        side_effect=ConnectionError("no redis in test"),
    ):
        t1 = threading.Thread(target=_worker, args=("a",))
        t2 = threading.Thread(target=_worker, args=("b",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

    assert len(order) == 4
    # Fully nested critical sections: enter/exit of one before the other starts
    assert order[0].endswith("-enter")
    assert order[1].endswith("-exit")
    assert order[2].endswith("-enter")
    assert order[3].endswith("-exit")
    assert order[0].split("-")[0] == order[1].split("-")[0]
    assert order[2].split("-")[0] == order[3].split("-")[0]
