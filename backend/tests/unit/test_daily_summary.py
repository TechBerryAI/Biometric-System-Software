"""Unit tests for daily attendance summary computation."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.domains.attendance.services.daily_summary_service import compute_daily_summary


@pytest.mark.testid("BE-UNIT-SUM-001")
def test_compute_daily_summary_empty_db_returns_list(db_session: Session) -> None:
    rows = compute_daily_summary(db_session, date(2026, 7, 14))
    assert isinstance(rows, list)
    assert rows == []
