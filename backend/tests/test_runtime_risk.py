"""Runtime risk and quarantine policy tests."""

from __future__ import annotations

import unittest

from app.models.device_runtime_health import DeviceRuntimeHealth
from app.services.device_command_service import _update_runtime_risk_level


class RuntimeRiskTests(unittest.TestCase):
    def test_risk_level_becomes_high_with_severe_penalties(self) -> None:
        row = DeviceRuntimeHealth(
            device_id="device-1",
            connection_stability_score=40,
            timeout_frequency=10,
            reconnect_frequency=8,
            protocol_error_rate=5,
            verification_failure_rate=4,
            drift_score=3,
        )
        _update_runtime_risk_level(row)
        self.assertEqual(row.operational_risk_level, "HIGH")

    def test_risk_level_stays_low_when_stable(self) -> None:
        row = DeviceRuntimeHealth(
            device_id="device-1",
            connection_stability_score=95,
            timeout_frequency=0,
            reconnect_frequency=0,
            protocol_error_rate=0,
            verification_failure_rate=0,
            drift_score=0,
        )
        _update_runtime_risk_level(row)
        self.assertEqual(row.operational_risk_level, "LOW")


if __name__ == "__main__":
    unittest.main()
