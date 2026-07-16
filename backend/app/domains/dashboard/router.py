"""Dashboard API — aggregated KPIs to avoid N+1 client fan-out."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_read_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.dashboard.services.dashboard_service import DashboardKpis, DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis", response_model=DashboardKpis)
def dashboard_kpis(
    request: Request,
    days: int = Query(7, ge=1, le=62),
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_read_db),
) -> DashboardKpis:
    tenant_id = None
    ctx = getattr(request.state, "tenant_context", None)
    if ctx is not None:
        tenant_id = ctx.tenant_id
    return DashboardService(get_settings()).get_kpis(db, days=days, tenant_id=tenant_id)
