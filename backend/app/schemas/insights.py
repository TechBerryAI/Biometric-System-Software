"""Compatibility exports for insights schemas."""

from app.ai.schemas.insight_models import AnomalyDetectionResponse, ManagementInsightsResponse

__all__ = [
    "ManagementInsightsResponse",
    "AnomalyDetectionResponse",
]
