"""Unit tests for payroll insights in InsightService."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.ai.services.insight_service import InsightService
from app.core.config import get_settings


@pytest.mark.testid("BE-UNIT-AI-PAY-001")
def test_payroll_insights_rules_fallback_without_api_key(db_session: Session) -> None:
    settings = get_settings().model_copy(update={"xai_api_key": ""})
    service = InsightService(settings)
    result = service.get_payroll_insights(db_session, days=7)

    assert result.available is True
    assert result.source == "rules"
    assert len(result.insights) >= 1
    assert result.insights[0].key in {"payroll_ready", "missing_checkouts", "incomplete_days", "overtime_exposure"}
