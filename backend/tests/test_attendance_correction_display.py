"""Tests for day summary display and device command reliability."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.models.device_command import DeviceCommandStatus
from app.services.attendance_helpers import summarize_employee_day_from_logs
from app.services.device_attlog_protocol import probe_attlog_capabilities
from app.services.device_command_service import claim_pending_commands


class _Punch:
    def __init__(self, ts: datetime, punch_type: str = "0") -> None:
        self.timestamp = ts
        self.punch_type = punch_type


class TierBConn:
    records = 0
    user_packet_size = 28

    def read_sizes(self) -> None:
        return None

    def clear_attendance(self) -> bool:
        return True

    def _send_with_buffer(self, _blob: bytes) -> None:
        return None


class DaySummaryDisplayTests(unittest.TestCase):
    def test_summarize_from_logs(self) -> None:
        tz = ZoneInfo("UTC")
        raw_in = datetime(2026, 7, 13, 9, 0, 0, tzinfo=tz)
        raw_out = datetime(2026, 7, 13, 18, 0, 0, tzinfo=tz)
        employee = SimpleNamespace(id=1, device_user_id="E001", employee_uuid="uuid-1")
        db = MagicMock()

        first_in, last_out, total_min, punch_count = summarize_employee_day_from_logs(
            db,
            employee=employee,
            local_date=date(2026, 7, 13),
            logs=[_Punch(raw_in, "0"), _Punch(raw_out, "1")],
        )

        self.assertEqual(first_in, raw_in)
        self.assertEqual(last_out, raw_out)
        self.assertEqual(punch_count, 2)
        self.assertIsNotNone(total_min)

    def test_summarize_empty_day(self) -> None:
        employee = SimpleNamespace(id=1, device_user_id="E001", employee_uuid="uuid-1")
        db = MagicMock()
        with patch(
            "app.services.attendance_helpers.load_logs_for_employee_day",
            return_value=[],
        ):
            first_in, last_out, total_min, punch_count = summarize_employee_day_from_logs(
                db,
                employee=employee,
                local_date=date(2026, 7, 13),
            )
        self.assertIsNone(first_in)
        self.assertIsNone(last_out)
        self.assertIsNone(total_min)
        self.assertEqual(punch_count, 0)


class DeviceCommandPriorityTests(unittest.TestCase):
    def test_claim_pending_prioritizes_correct_attendance(self) -> None:
        now = datetime.now(ZoneInfo("UTC"))
        upsert = SimpleNamespace(
            device_id="main-entrance",
            command_type="UPSERT_USER",
            created_at=now,
            status=DeviceCommandStatus.PENDING.value,
            started_at=None,
            heartbeat_at=None,
        )
        correct = SimpleNamespace(
            device_id="main-entrance",
            command_type="CORRECT_ATTENDANCE",
            created_at=now,
            status=DeviceCommandStatus.PENDING.value,
            started_at=None,
            heartbeat_at=None,
        )

        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [upsert, correct]

        claimed = claim_pending_commands(db)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].command_type, "CORRECT_ATTENDANCE")
        self.assertEqual(claimed[0].status, DeviceCommandStatus.RUNNING.value)


class TierBWriteFlagTests(unittest.TestCase):
    def test_tier_b_read_only_by_default(self) -> None:
        caps = probe_attlog_capabilities(TierBConn())
        self.assertEqual(caps.tier, "B")
        self.assertFalse(caps.supports_write)

    def test_tier_b_write_when_flag_enabled(self) -> None:
        caps = probe_attlog_capabilities(TierBConn(), allow_tier_b_write=True)
        self.assertEqual(caps.tier, "B")
        self.assertTrue(caps.supports_write)
        self.assertTrue(caps.supports_full_rewrite)


if __name__ == "__main__":
    unittest.main()
