"""Unit tests for dashboard KPI aggregation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domains.dashboard.services.dashboard_service import DashboardService
from app.domains.employees.models.employee import Employee


@pytest.mark.testid("BE-UNIT-DASH-001")
def test_dashboard_kpis_aggregates(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_FLAGS", "dashboard_cache=false")
    from app.core.config import get_settings
    from app.core.feature_flags import reset_feature_flags

    get_settings.cache_clear()
    reset_feature_flags()

    db_session.add(Employee(device_user_id="10", name="Ada"))
    db_session.commit()

    service = DashboardService(get_settings(), cache=MagicMock(get_json=MagicMock(return_value=None)))
    kpis = service.get_kpis(db_session, days=7, use_cache=False)
    assert kpis.active_employees >= 1
    assert kpis.cache_hit is False
    get_settings.cache_clear()
    reset_feature_flags()
