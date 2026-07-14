"""Unit tests for anomaly heuristic detection."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ai.services.anomaly_service import AnomalyService, _DayFeatures, _severity_from_score
from app.core.config import get_settings


def _features(day: date, *, overtime_rate: float = 5.0, absenteeism_rate: float = 5.0) -> _DayFeatures:
    return _DayFeatures(
        day=day,
        attendance_rate=90.0,
        avg_work_minutes=480.0,
        missing_checkout_rate=5.0,
        overtime_rate=overtime_rate,
        offhour_checkin_rate=2.0,
        absenteeism_rate=absenteeism_rate,
    )


@pytest.mark.testid("BE-UNIT-AI-ANOM-001")
def test_severity_from_score() -> None:
    assert _severity_from_score(3.5).value == "critical"
    assert _severity_from_score(2.1).value == "high"
    assert _severity_from_score(1.5).value == "medium"
    assert _severity_from_score(0.5).value == "low"


@pytest.mark.testid("BE-UNIT-AI-ANOM-001")
def test_detect_builds_overtime_spike_when_rates_high() -> None:
    """Use 7–9 days so detector stays on the heuristic path (not IsolationForest)."""
    start = date(2026, 1, 1)
    rows = [_features(start + timedelta(days=i), overtime_rate=5.0) for i in range(6)]
    rows.append(_features(start + timedelta(days=6), overtime_rate=40.0))

    service = AnomalyService(get_settings())
    anomalies, detector = service._detect(rows)

    assert detector == "heuristic"
    assert any(a.anomaly_key == "overtime_spike" for a in anomalies)
