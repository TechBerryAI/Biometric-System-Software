"""API tests for /reporting* endpoints."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.domains.reporting.schemas import AttendanceHeatmapResponse, BranchComparisonResponse, DeviceUptimeResponse

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-API-REPORT-001")
def test_attendance_heatmap(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = AttendanceHeatmapResponse(
        period_start=today,
        period_end=today,
        generated_at=datetime.now(UTC),
        cells=[],
    )
    with patch(
        "app.domains.reporting.router.ReportingService.attendance_heatmap",
        return_value=fake,
    ):
        response = client.get("/reporting/heatmap", headers=admin_headers, params={"days": 14})
    assert response.status_code == 200
    assert response.json()["cells"] == []


@pytest.mark.testid("BE-API-REPORT-002")
def test_branch_comparison(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = BranchComparisonResponse(
        period_start=today,
        period_end=today,
        generated_at=datetime.now(UTC),
        branches=[],
    )
    with patch(
        "app.domains.reporting.router.ReportingService.branch_comparison",
        return_value=fake,
    ):
        response = client.get("/reporting/branch-comparison", headers=admin_headers)
    assert response.status_code == 200


@pytest.mark.testid("BE-API-REPORT-003")
def test_device_uptime(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = DeviceUptimeResponse(
        period_start=today,
        period_end=today,
        generated_at=datetime.now(UTC),
        devices=[],
    )
    with patch(
        "app.domains.reporting.router.ReportingService.device_uptime",
        return_value=fake,
    ):
        response = client.get("/reporting/device-uptime", headers=admin_headers)
    assert response.status_code == 200
