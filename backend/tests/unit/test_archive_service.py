"""Unit tests for attendance archive service."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.config import get_settings
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.archive_service import archive_old_attendance


@pytest.mark.testid("BE-UNIT-ARCH-001")
def test_archive_skips_when_no_old_rows(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTENDANCE_ARCHIVE_RETENTION_DAYS", "30")
    get_settings.cache_clear()
    result = archive_old_attendance(db_session, settings=get_settings(), dry_run=True)
    assert result.get("skipped") is True
    get_settings.cache_clear()


@pytest.mark.testid("BE-UNIT-ARCH-002")
def test_archive_records_run_for_old_rows(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTENDANCE_ARCHIVE_RETENTION_DAYS", "30")
    monkeypatch.setenv("ATTENDANCE_ARCHIVE_DELETE", "false")
    get_settings.cache_clear()
    old_ts = datetime.now(ZoneInfo("UTC")) - timedelta(days=90)
    db_session.add(
        AttendanceLog(
            employee_code="1",
            timestamp=old_ts,
            device_id="main-entrance",
            punch_type="check_in",
        )
    )
    db_session.commit()
    result = archive_old_attendance(db_session, settings=get_settings())
    db_session.commit()
    assert result["eligible"] >= 1
    assert result["status"] == "recorded"
    assert result["archived"] == 0
    get_settings.cache_clear()
