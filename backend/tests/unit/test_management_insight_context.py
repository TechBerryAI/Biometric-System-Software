"""Unit tests for management insight context builder."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ai.services.management_insight_context import build_management_insight_context


@pytest.mark.testid("BE-UNIT-AI-CTX-001")
def test_build_management_insight_context_empty_employees(db_session: Session) -> None:
    ctx = build_management_insight_context(db_session, get_settings(), trend_days=3)
    assert ctx["roster_size"] == 0
    assert ctx["trend_days"] == 3
    assert isinstance(ctx["daily_trend"], list)
    assert len(ctx["daily_trend"]) == 3
    assert ctx["department_today"] == []
    for day in ctx["daily_trend"]:
        assert day["headcount"] == 0
        assert day["present"] == 0
