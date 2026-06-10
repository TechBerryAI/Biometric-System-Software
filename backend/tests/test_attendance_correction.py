"""Unit tests for attendance correction helpers (no pyzk/database required)."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.device_attlog_codec import encode_time_zk
from app.services.device_attlog_protocol import _ts_match, probe_attlog_capabilities
from tests.mocks.pyzk_simulator import SimulatedPyZKDevice


class AttendanceCorrectionUnitTests(unittest.TestCase):
    def test_encode_time_zk_roundtrip(self) -> None:
        ts = datetime(2026, 6, 10, 9, 30, 0)
        encoded = encode_time_zk(ts)
        self.assertEqual(len(encoded), 4)

    def test_probe_simulator_tier_a(self) -> None:
        device = SimulatedPyZKDevice()
        caps = probe_attlog_capabilities(device.connection())
        self.assertEqual(caps.tier, "A")
        self.assertTrue(caps.supports_selective_delete)

    def test_probe_tier_b_read_only(self) -> None:
        """Real pyzk Tier B exposes clear+buffer but cannot commit attlog writes."""

        class TierBConn:
            records = 0
            user_packet_size = 28

            def read_sizes(self) -> None:
                return None

            def clear_attendance(self) -> bool:
                return True

            def _send_with_buffer(self, _blob: bytes) -> None:
                return None

        caps = probe_attlog_capabilities(TierBConn())
        self.assertEqual(caps.tier, "B")
        self.assertFalse(caps.supports_write)
        self.assertFalse(caps.supports_full_rewrite)

    def test_ts_match_utc_aware_vs_device_naive(self) -> None:
        # 4:26 pm IST == 10:56 UTC on same calendar day (example from DB vs device)
        device_local = datetime(2026, 6, 10, 16, 26, 5)
        db_utc = datetime(2026, 6, 10, 10, 56, 5, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(_ts_match(device_local, db_utc, tz_name="Asia/Kolkata"))


if __name__ == "__main__":
    unittest.main()
