"""AI insights API: management summaries, anomalies, reports, and copilot."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.services.anomaly_service import AnomalyService
from app.ai.services.copilot_service import CopilotService
from app.ai.services.forecasting_service import ForecastingService
from app.ai.services.insight_service import InsightService
from app.ai.services.reporting_service import ReportingService
from app.ai.utils.governance import AIGovernance
from app.ai.utils.metrics import snapshot as ai_metrics_snapshot
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.user import User
from app.schemas.insights import (
    AnomalyDetectionResponse,
    CopilotQueryRequest,
    CopilotQueryResponse,
    ExecutiveReportResponse,
    ForecastResponse,
    ManagementInsightsResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/management", response_model=ManagementInsightsResponse)
def management_insights(
    days: int = Query(14, ge=3, le=62, description="Trailing calendar days in TIMEZONE (oldest first in context)."),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> ManagementInsightsResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = InsightService(settings)
    return service.get_management_insights(db, days=days)


@router.get("/anomalies", response_model=AnomalyDetectionResponse)
def attendance_anomalies(
    lookback_days: int = Query(30, ge=7, le=90),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> AnomalyDetectionResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = AnomalyService(settings)
    return service.detect_and_explain(db, lookback_days=lookback_days)


@router.get("/forecast", response_model=ForecastResponse)
def forecast_attendance(
    lookback_days: int = Query(30, ge=7, le=90),
    horizon_days: int = Query(7, ge=3, le=30),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = ForecastingService(settings)
    return service.forecast(db, lookback_days=lookback_days, horizon_days=horizon_days)


@router.get("/reports/{report_type}", response_model=ExecutiveReportResponse)
def executive_report(
    report_type: Literal["weekly", "monthly", "department"],
    department: str | None = Query(None, min_length=1, max_length=255),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> ExecutiveReportResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = ReportingService(settings)
    return service.generate_report(db, report_type=report_type, department=department)


@router.post("/copilot/query", response_model=CopilotQueryResponse)
def copilot_query(
    request: CopilotQueryRequest,
    _user: User = Depends(require_permissions(Permission.AI_ADMIN)),
    db: Session = Depends(get_db),
) -> CopilotQueryResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = CopilotService(settings)
    return service.answer(db, request)


@router.get("/metrics", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def ai_metrics() -> dict[str, int]:
    return ai_metrics_snapshot()


