"""AI insights API: management summaries and anomaly detection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.services.anomaly_service import AnomalyService
from app.ai.services.insight_service import InsightService
from app.ai.utils.governance import AIGovernance
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.user import User
from app.schemas.insights import AnomalyDetectionResponse, ManagementInsightsResponse

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
