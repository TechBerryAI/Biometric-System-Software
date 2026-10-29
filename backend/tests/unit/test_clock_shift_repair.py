"""Repair 12h AM/PM punch stamps and skip re-ingest of original device times."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.app_timezone import as_aware, set_app_timezone
from app.core.config import get_settings
from app.domains.attendance.models.attendance_ingest_skip import AttendanceIngestSkip
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.clock_shift_repair import (
    repair_twelve_hour_clock_shift,
)
from app.domains.attendance.services.attendance_service import run_device_sync_detailed
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_attendance_log, make_employee

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


def _stored_ist(ts: datetime) -> datetime:
    """Stamps are stored as UTC; SQLite returns them naive, so never let the host zone interpret them."""
    return as_aware(ts, UTC).astimezone(IST)


def _lagged_log(employee, *, punch_ist: datetime, created_ist: datetime, punch_type: str = "0") -> AttendanceLog:
    log = make_attendance_log(
        employee=employee,
        punched_at=punch_ist.astimezone(UTC),
        punch_type=punch_type,
    )
    log.created_at = created_ist.astimezone(UTC)
    return log


@pytest.fixture()
def ist_settings(monkeypatch: pytest.MonkeyPatch):
    set_app_timezone("Asia/Kolkata")
    monkeypatch.setattr(get_settings(), "timezone", "Asia/Kolkata")
    yield
    set_app_timezone(None)


@pytest.mark.testid("BE-UNIT-SHIFT-001")
def test_twelve_hour_repair_moves_sunday_night_to_monday(db_session: Session, ist_settings) -> None:
    emp = make_employee(device_user_id="TBI12H01")
    friday_morning = _lagged_log(
        emp,
        punch_ist=datetime(2026, 8, 21, 9, 10, tzinfo=IST),
        created_ist=datetime(2026, 8, 21, 9, 12, tzinfo=IST),
    )
    sunday_night = _lagged_log(
        emp,
        punch_ist=datetime(2026, 8, 23, 21, 30, tzinfo=IST),
        created_ist=datetime(2026, 8, 24, 9, 34, tzinfo=IST),
    )
    db_session.add_all([emp, friday_morning, sunday_night])
    db_session.commit()

    dry = repair_twelve_hour_clock_shift(db_session, apply=False)
    assert dry.matched == 1
    assert dry.updated == 0

    applied = repair_twelve_hour_clock_shift(db_session, apply=True)
    assert applied.matched == 1
    assert applied.updated == 1
    assert applied.skip_rows == 1

    db_session.refresh(friday_morning)
    db_session.refresh(sunday_night)
    assert _stored_ist(friday_morning.timestamp) == datetime(2026, 8, 21, 9, 10, tzinfo=IST)
    assert _stored_ist(sunday_night.timestamp) == datetime(2026, 8, 24, 9, 30, tzinfo=IST)

    skips = list(db_session.execute(select(AttendanceIngestSkip)).scalars().all())
    assert len(skips) == 1
    assert _stored_ist(skips[0].timestamp) == datetime(2026, 8, 23, 21, 30, tzinfo=IST)

    again = repair_twelve_hour_clock_shift(db_session, apply=True)
    assert again.matched == 0
    assert again.deleted_duplicates == 0


@pytest.mark.testid("BE-UNIT-SHIFT-003")
def test_twelve_hour_repair_deletes_reimported_duplicate(db_session: Session, ist_settings) -> None:
    emp = make_employee(device_user_id="TBI12H03")
    original_ist = datetime(2026, 8, 23, 21, 52, 21, tzinfo=IST)
    lagged = _lagged_log(
        emp,
        punch_ist=original_ist,
        created_ist=datetime(2026, 8, 24, 9, 56, tzinfo=IST),
    )
    already_fixed = make_attendance_log(
        employee=emp,
        punched_at=(original_ist + timedelta(hours=12)).astimezone(UTC),
        punch_type="0",
    )
    already_fixed.created_at = datetime(2026, 8, 24, 9, 34, tzinfo=IST).astimezone(UTC)
    db_session.add_all([emp, lagged, already_fixed])
    db_session.commit()

    report = repair_twelve_hour_clock_shift(db_session, apply=True)
    assert report.deleted_duplicates == 1
    assert report.updated == 0
    remaining = list(db_session.execute(select(AttendanceLog)).scalars().all())
    assert len(remaining) == 1
    assert remaining[0].id == already_fixed.id


@pytest.mark.testid("BE-INT-SHIFT-002")
def test_repaired_original_stamps_are_not_reinserted(db_session: Session, ist_settings) -> None:
    emp = make_employee(device_user_id="TBI12H02")
    original_ist = datetime(2026, 8, 23, 21, 30, tzinfo=IST)
    log = _lagged_log(
        emp,
        punch_ist=original_ist,
        created_ist=datetime(2026, 8, 24, 9, 34, tzinfo=IST),
    )
    db_session.add_all([emp, log])
    db_session.commit()

    repair_twelve_hour_clock_shift(db_session, apply=True)

    fake = MagicMock()
    fake.fetch_attendance.return_value = [
        DeviceAttendanceRecord(user_id="TBI12H02", timestamp=original_ist, punch=0, status=0),
    ]
    fake.last_clock_drift_seconds = 0.0
    result = run_device_sync_detailed(
        db_session, device=fake, full_resync=True, device_id="main-entrance"
    )
    assert result.skipped_repaired_punches == 1
    assert result.inserted == 0
    rows = list(db_session.execute(select(AttendanceLog)).scalars().all())
    assert len(rows) == 1
    assert _stored_ist(rows[0].timestamp) == datetime(2026, 8, 24, 9, 30, tzinfo=IST)


@pytest.mark.testid("BE-UNIT-SHIFT-004")
def test_purge_deletes_skip_originals_outside_lag_window(db_session: Session, ist_settings) -> None:
    emp = make_employee(device_user_id="TBI12H04")
    original_ist = datetime(2026, 8, 22, 0, 27, tzinfo=IST)
    repaired_ist = original_ist + timedelta(hours=12)
    reimported = make_attendance_log(
        employee=emp,
        punched_at=original_ist.astimezone(UTC),
        punch_type="0",
    )
    reimported.created_at = datetime(2026, 8, 24, 10, 50, tzinfo=IST).astimezone(UTC)
    kept = make_attendance_log(
        employee=emp,
        punched_at=repaired_ist.astimezone(UTC),
        punch_type="0",
    )
    skip = AttendanceIngestSkip(
        device_id=reimported.device_id,
        employee_code=emp.device_user_id,
        timestamp=original_ist.astimezone(UTC),
        punch_type="0",
        repaired_timestamp=repaired_ist.astimezone(UTC),
    )
    db_session.add_all([emp, reimported, kept, skip])
    db_session.commit()

    report = repair_twelve_hour_clock_shift(db_session, apply=True)
    assert report.matched == 0
    assert report.deleted_duplicates == 1
    remaining = list(db_session.execute(select(AttendanceLog)).scalars().all())
    assert len(remaining) == 1
    assert remaining[0].id == kept.id
    assert _stored_ist(remaining[0].timestamp) == repaired_ist
