"""AI insights API: management summaries and anomaly detection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.services.anomaly_service import AnomalyService
from app.ai.services.buddy_punch_service import BuddyPunchService
from app.ai.services.device_failure_prediction import DeviceFailurePredictionService
from app.ai.services.insight_service import InsightService
from app.ai.services.prediction_service import PredictionService
from app.ai.utils.governance import AIGovernance
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.ai.schemas.http_insights import (
    AnomalyDetectionResponse,
    AttendancePredictionResponse,
    BuddyPunchResponse,
    DeviceFailurePredictionResponse,
    ManagementInsightsResponse,
    PayrollInsightsResponse,
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


@router.get("/predictions/attendance", response_model=AttendancePredictionResponse)
def attendance_predictions(
    history_days: int = Query(14, ge=7, le=62),
    horizon_days: int = Query(7, ge=1, le=14),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> AttendancePredictionResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = PredictionService(settings)
    return service.predict_attendance(db, history_days=history_days, horizon_days=horizon_days)


@router.get("/buddy-punch", response_model=BuddyPunchResponse)
def buddy_punch_alerts(
    lookback_days: int = Query(14, ge=1, le=90),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> BuddyPunchResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = BuddyPunchService(settings)
    return service.detect(db, lookback_days=lookback_days)


@router.get("/predictions/device-failures", response_model=DeviceFailurePredictionResponse)
def device_failure_predictions(
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> DeviceFailurePredictionResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = DeviceFailurePredictionService(settings)
    return service.predict(db)


@router.get("/payroll", response_model=PayrollInsightsResponse)
def payroll_insights(
    days: int = Query(14, ge=3, le=62),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> PayrollInsightsResponse:
    settings = get_settings()
    AIGovernance(settings).assert_allowed(_user.user_uuid)
    service = InsightService(settings)
    return service.get_payroll_insights(db, days=days)
