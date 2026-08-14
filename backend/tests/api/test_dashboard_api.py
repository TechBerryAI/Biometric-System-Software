"""API tests for dashboard KPIs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_read_db
from app.main import app


@pytest.fixture()
def _override_read_db(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_read_db] = _override
    yield
    app.dependency_overrides.pop(get_read_db, None)


@pytest.mark.testid("BE-API-DASH-001")
def test_dashboard_kpis_requires_auth(client: TestClient) -> None:
    response = client.get("/dashboard/kpis")
    assert response.status_code in {401, 403}


@pytest.mark.testid("BE-API-DASH-002")
def test_dashboard_kpis_ok(client: TestClient, admin_headers: dict[str, str], _override_read_db) -> None:
    response = client.get("/dashboard/kpis?days=7", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "active_employees" in body
    assert "punches_today" in body
    assert "devices_total" in body
