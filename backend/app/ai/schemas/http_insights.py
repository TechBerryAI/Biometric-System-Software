"""Compatibility exports for insights schemas."""

from app.ai.schemas.insight_models import (
    AnomalyDetectionResponse,
    AttendancePredictionResponse,
    BuddyPunchResponse,
    DeviceFailurePredictionResponse,
    ManagementInsightsResponse,
    PayrollInsightsResponse,
)

__all__ = [
    "ManagementInsightsResponse",
    "AnomalyDetectionResponse",
    "AttendancePredictionResponse",
    "BuddyPunchResponse",
    "DeviceFailurePredictionResponse",
    "PayrollInsightsResponse",
]
