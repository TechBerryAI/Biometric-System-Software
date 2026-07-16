"""Tenancy API for tenant selection in SaaS mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.auth.models.user import User
from app.domains.tenancy.models.hierarchy import Tenant

router = APIRouter(prefix="/tenants", tags=["tenancy"])


class TenantRead(BaseModel):
    id: int
    tenant_uuid: str
    name: str
    slug: str
    active: bool


@router.get("", response_model=list[TenantRead])
def list_tenants(
    _user: User = Depends(require_permissions(Permission.REPORT_READ)),
    db: Session = Depends(get_db),
) -> list[TenantRead]:
    rows = db.execute(select(Tenant).where(Tenant.active.is_(True)).order_by(Tenant.name)).scalars().all()
    return [
        TenantRead(
            id=row.id,
            tenant_uuid=row.tenant_uuid,
            name=row.name,
            slug=row.slug,
            active=row.active,
        )
        for row in rows
    ]
