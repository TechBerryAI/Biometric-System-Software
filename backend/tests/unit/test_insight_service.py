"""Unit tests for management InsightService degrade paths."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.ai.services.insight_service import InsightService
from app.core.config import Settings, get_settings


@pytest.mark.testid("BE-UNIT-AI-INS-001")
def test_insight_service_degrades_without_api_key(db_session: Session) -> None:
    settings = get_settings().model_copy(update={"xai_api_key": ""})
    service = InsightService(settings)
    result = service.get_management_insights(db_session, days=7)

    assert result.available is False
    assert result.source == "unconfigured"
    assert result.error_code == "xai_api_key_missing"
    assert result.bullets == []


@pytest.mark.testid("BE-UNIT-AI-INS-001")
def test_insight_service_degrades_when_key_none(db_session: Session) -> None:
    base = get_settings()
    settings = Settings(**{**base.model_dump(), "xai_api_key": None})
    service = InsightService(settings)
    result = service.get_management_insights(db_session)
    assert result.available is False
    assert result.error_code == "xai_api_key_missing"
