"""Tests for append-only attendance architecture and punch direction handling."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.attendance_helpers import (
    DayAttendanceSnapshot,
    _first_meaningful_check_in,
    verify_imported_timestamps,
)
from app.services.attendance_service import prune_recent_duplicate_logs
from app.core.config import get_settings
from app.services.punch_classification import (
    device_attendance_punch_type,
    resolve_punch_types_for_day,
    summarize_day_punches,
)


class _Punch:
    def __init__(self, ts: datetime, punch_type: str) -> None:
        self.timestamp = ts
        self.punch_type = punch_type


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
            first_check_in=None,
            last_check_out=None,
            log_ids=[],
            log_timestamps=[],
        )
        self.assertIsNone(snap.first_check_in)
        self.assertEqual(snap.log_ids, [])

    def test_device_attendance_punch_type_uses_status_not_verify_mode(self) -> None:
        self.assertEqual(device_attendance_punch_type(status=0, punch=1), "0")
        self.assertEqual(device_attendance_punch_type(status=1, punch=1), "1")

    def test_resolve_legacy_fingerprint_rows_alternates(self) -> None:
        repaired = resolve_punch_types_for_day(["1", "1"])
        self.assertEqual(repaired, ["0", "1"])

    def test_summarize_single_punch_treated_as_check_in(self) -> None:
        ts = datetime(2026, 6, 19, 18, 30, 20, tzinfo=ZoneInfo("UTC"))
        first_in, last_out, work = summarize_day_punches([_Punch(ts, "1")])
        self.assertEqual(first_in, ts)
        self.assertIsNone(last_out)
        self.assertIsNone(work)

    def test_single_morning_fingerprint_reclassified_as_check_in(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")
        ts = datetime(2026, 6, 18, 9, 15, 0, tzinfo=tz)
        first_in, last_out, work = summarize_day_punches([_Punch(ts, "1")], tz_name="Asia/Kolkata")
        self.assertEqual(first_in, ts)
        self.assertIsNone(last_out)
        self.assertIsNone(work)

    def test_summarize_pairs_legacy_in_out_day(self) -> None:
        tz = ZoneInfo("UTC")
        punches = [
            _Punch(datetime(2026, 6, 18, 9, 36, 56, tzinfo=tz), "1"),
            _Punch(datetime(2026, 6, 18, 18, 26, 54, tzinfo=tz), "1"),
        ]
        first_in, last_out, work = summarize_day_punches(punches)
        self.assertEqual(first_in, punches[0].timestamp)
        self.assertEqual(last_out, punches[1].timestamp)
        self.assertEqual(work, 529)

    def test_first_meaningful_check_in_skips_enrollment_orphan(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")
        enrollment = datetime(2025, 12, 17, 14, 57, 23, tzinfo=tz)
        first_work = datetime(2026, 4, 28, 14, 47, 56, tzinfo=tz)
        check_ins = [
            (enrollment, enrollment.date(), 1),
            (first_work, first_work.date(), 1),
        ]
        all_ts = [enrollment, first_work]
        self.assertEqual(_first_meaningful_check_in(check_ins, all_ts), first_work)

    def test_first_meaningful_check_in_keeps_nearby_singleton(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")
        first = datetime(2026, 4, 28, 9, 0, 0, tzinfo=tz)
        second = datetime(2026, 5, 3, 9, 0, 0, tzinfo=tz)
        check_ins = [(first, first.date(), 1)]
        self.assertEqual(_first_meaningful_check_in(check_ins, [first, second]), first)


if __name__ == "__main__":
    unittest.main()
