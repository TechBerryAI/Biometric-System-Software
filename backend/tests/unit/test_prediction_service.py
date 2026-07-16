"""Unit tests for attendance PredictionService."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.ai.services.prediction_service import PredictionService
from app.core.config import get_settings
from tests.factories import make_attendance_log, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-UNIT-AI-PRED-001")
def test_prediction_service_returns_insufficient_data_without_history(db_session: Session) -> None:
    service = PredictionService(get_settings())
    result = service.predict_attendance(db_session, history_days=14, horizon_days=7)
    assert result.source == "insufficient_data"
    assert result.predictions == []


@pytest.mark.testid("BE-UNIT-AI-PRED-002")
def test_prediction_service_forecasts_from_history(db_session: Session) -> None:
    settings = get_settings()
    service = PredictionService(settings)
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()

    for offset in range(10):
        emp = make_employee(device_user_id=f"EMP{offset:03d}")
        db_session.add(emp)
        db_session.flush()
        day = today - timedelta(days=9 - offset)
        ts = datetime.combine(day, datetime.min.time().replace(hour=9), tzinfo=tz).astimezone(UTC)
        db_session.add(make_attendance_log(employee=emp, punched_at=ts, punch_type="0"))
        db_session.add(
            make_attendance_log(
                employee=emp,
                punched_at=ts + timedelta(hours=8),
                punch_type="1",
            )
        )
    db_session.commit()

    result = service.predict_attendance(db_session, history_days=14, horizon_days=3)
    assert result.source == "heuristic"
    assert len(result.predictions) == 3
    assert result.predictions[0].predicted_present >= 0
