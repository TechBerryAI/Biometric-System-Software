"""Reporting analytics API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.reporting.schemas import (
    AttendanceHeatmapResponse,
    BranchComparisonResponse,
    DeviceUptimeResponse,
)
from app.domains.reporting.services.reporting_service import ReportingService

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/heatmap", response_model=AttendanceHeatmapResponse)
def attendance_heatmap(
    days: int = Query(14, ge=1, le=62),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> AttendanceHeatmapResponse:
    service = ReportingService(get_settings())
    return service.attendance_heatmap(db, days=days)


@router.get("/branch-comparison", response_model=BranchComparisonResponse)
def branch_comparison(
    days: int = Query(14, ge=1, le=62),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> BranchComparisonResponse:
    service = ReportingService(get_settings())
    return service.branch_comparison(db, days=days)


@router.get("/device-uptime", response_model=DeviceUptimeResponse)
def device_uptime(
    days: int = Query(7, ge=1, le=31),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> DeviceUptimeResponse:
    service = ReportingService(get_settings())
    return service.device_uptime(db, days=days)
