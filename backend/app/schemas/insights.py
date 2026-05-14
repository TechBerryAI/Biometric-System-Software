"""Compatibility exports for insights schemas."""

from app.ai.schemas.insight_models import (
    AnomalyDetectionResponse,
    CopilotQueryRequest,
    CopilotQueryResponse,
    ExecutiveReportResponse,
    ForecastResponse,
    ManagementInsightsResponse,
)

__all__ = [
    "ManagementInsightsResponse",
    "AnomalyDetectionResponse",
    "ExecutiveReportResponse",
    "ForecastResponse",
    "CopilotQueryRequest",
    "CopilotQueryResponse",
]
