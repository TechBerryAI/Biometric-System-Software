"""Unit tests for correction-day sync guards."""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.domains.attendance.services.attendance_correction_service import (
    is_punch_blocked_by_correction,
    load_corrected_day_guards,
    load_corrected_employee_days,
)
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from tests.factories import make_device

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.testid("BE-UNIT-CORR-GUARD-001")
def test_morning_correction_allows_midday_and_evening_despite_late_completed_at(
    db_session: Session,
) -> None:
    """Late-processed morning correction must not wall off midday punches via completed_at."""
    device = make_device(name="main-entrance")
    db_session.add(device)
    db_session.flush()
    morning = datetime(2026, 7, 21, 9, 33, 19, tzinfo=IST)
    deleted_near = datetime(2026, 7, 21, 9, 49, 19, tzinfo=IST)
    # Correction command finished in the afternoon — must NOT extend protect_until.
    completed = datetime(2026, 7, 21, 14, 3, 41, tzinfo=IST)
    db_session.add(
        DeviceCommand(
            device_id="main-entrance",
            command_type="CORRECT_ATTENDANCE",
            status=DeviceCommandStatus.SUCCESS.value,
            payload={
                "user_id": "TBC262",
                "local_date": "2026-07-21",
                "new_check_in": morning.isoformat(),
                "new_check_out": None,
                "delete_timestamps": [deleted_near.isoformat()],
            },
            idempotency_key=f"test-corr-guard-{uuid4()}",
            completed_at=completed,
            created_at=completed,
        )
    )
    db_session.commit()

    guards = load_corrected_day_guards(db_session, device_id="main-entrance")
    assert ("TBC262", date(2026, 7, 21)) in guards
    assert ("TBC262", date(2026, 7, 21)) in load_corrected_employee_days(
        db_session, device_id="main-entrance"
    )
    # protect_until must be the deleted near-dup (09:49 IST), not completed_at (14:03 IST)
    protect_until = guards[("TBC262", date(2026, 7, 21))]
    assert protect_until == deleted_near

    midday = datetime(2026, 7, 21, 12, 0, 0, tzinfo=IST)
    evening = datetime(2026, 7, 21, 18, 30, 0, tzinfo=IST)
    assert is_punch_blocked_by_correction(
        user_id="TBC262",
        timestamp=deleted_near,
        local_day=date(2026, 7, 21),
        guards=guards,
    )
    assert not is_punch_blocked_by_correction(
        user_id="TBC262",
        timestamp=midday,
        local_day=date(2026, 7, 21),
        guards=guards,
    )
    assert not is_punch_blocked_by_correction(
        user_id="TBC262",
        timestamp=evening,
        local_day=date(2026, 7, 21),
        guards=guards,
    )
