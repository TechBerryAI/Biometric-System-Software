"""Tests for append-only attendance architecture."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.attendance_effective_service import DayAttendanceSnapshot, verify_imported_timestamps
from app.services.attendance_service import prune_recent_duplicate_logs
from app.core.config import get_settings


class AttendanceArchitectureTests(unittest.TestCase):
    def test_prune_is_noop(self) -> None:
        class FakeSession:
            pass

        self.assertEqual(prune_recent_duplicate_logs(FakeSession(), settings=get_settings()), 0)

    def test_verify_imported_timestamps(self) -> None:
        expected_in = datetime(2026, 6, 10, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        expected_out = datetime(2026, 6, 10, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        imported = [expected_in, expected_out]
        has_in, has_out = verify_imported_timestamps(
            expected_in=expected_in,
            expected_out=expected_out,
            imported_timestamps=imported,
            tz_name="Asia/Kolkata",
        )
        self.assertTrue(has_in)
        self.assertTrue(has_out)

    def test_day_snapshot_dataclass(self) -> None:
        snap = DayAttendanceSnapshot(
            local_date=date(2026, 6, 10),
            first_check_in=None,
            last_check_out=None,
            log_ids=[],
            log_timestamps=[],
        )
        self.assertEqual(snap.local_date.isoformat(), "2026-06-10")


if __name__ == "__main__":
    unittest.main()
