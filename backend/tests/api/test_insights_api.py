"""API tests for /insights* endpoints."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.ai.schemas.insight_models import (
    AnomalyDetectionResponse,
    AttendancePredictionResponse,
    BuddyPunchResponse,
    DeviceFailurePredictionResponse,
    ManagementInsightsResponse,
    PayrollInsightsResponse,
)

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-API-INS-001")
def test_management_insights(client: TestClient, admin_headers: dict[str, str]) -> None:
    fake = ManagementInsightsResponse(
        available=True,
        source="rules",
        bullets=["Attendance is stable."],
        confidence="medium",
        risk_flags=[],
        cached=False,
    )
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch(
            "app.ai.router.InsightService.get_management_insights",
            return_value=fake,
        ),
    ):
        response = client.get("/insights/management", headers=admin_headers, params={"days": 14})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["source"] == "rules"
    assert body["bullets"] == ["Attendance is stable."]


@pytest.mark.testid("BE-API-INS-002")
def test_anomalies(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = AnomalyDetectionResponse(
        period_start=today,
        period_end=today,
        generated_at=datetime.now(UTC),
        detector="heuristic",
        anomalies=[],
        cached=False,
    )
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch(
            "app.ai.router.AnomalyService.detect_and_explain",
            return_value=fake,
        ),
    ):
        response = client.get(
            "/insights/anomalies",
            headers=admin_headers,
            params={"lookback_days": 30},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["detector"] == "heuristic"
    assert body["anomalies"] == []


@pytest.mark.testid("BE-API-INS-003")
def test_insights_degrade_without_api_key(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    with patch("app.ai.router.AIGovernance.assert_allowed"):
        response = client.get("/insights/management", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["source"] == "unconfigured"
    assert body.get("error_code") == "xai_api_key_missing"


@pytest.mark.testid("BE-API-INS-004")
def test_attendance_predictions(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = AttendancePredictionResponse(
        period_start=today,
        period_end=today,
        generated_at=datetime.now(UTC),
        horizon_days=7,
        source="heuristic",
        predictions=[],
    )
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch("app.ai.router.PredictionService.predict_attendance", return_value=fake),
    ):
        response = client.get("/insights/predictions/attendance", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["source"] == "heuristic"


@pytest.mark.testid("BE-API-INS-005")
def test_buddy_punch(client: TestClient, admin_headers: dict[str, str]) -> None:
    fake = BuddyPunchResponse(lookback_days=14, generated_at=datetime.now(UTC), alerts=[])
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch("app.ai.router.BuddyPunchService.detect", return_value=fake),
    ):
        response = client.get("/insights/buddy-punch", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["alerts"] == []


@pytest.mark.testid("BE-API-INS-006")
def test_device_failure_predictions(client: TestClient, admin_headers: dict[str, str]) -> None:
    fake = DeviceFailurePredictionResponse(generated_at=datetime.now(UTC), devices=[])
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch("app.ai.router.DeviceFailurePredictionService.predict", return_value=fake),
    ):
        response = client.get("/insights/predictions/device-failures", headers=admin_headers)
    assert response.status_code == 200


@pytest.mark.testid("BE-API-INS-007")
def test_payroll_insights(client: TestClient, admin_headers: dict[str, str]) -> None:
    today = date.today()
    fake = PayrollInsightsResponse(
        period_start=today,
        period_end=today,
        available=True,
        source="rules",
        insights=[],
    )
    with (
        patch("app.ai.router.AIGovernance.assert_allowed"),
        patch("app.ai.router.InsightService.get_payroll_insights", return_value=fake),
    ):
        response = client.get("/insights/payroll", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["source"] == "rules"

