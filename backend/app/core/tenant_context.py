"""Tenant context resolution for hybrid SaaS/dedicated deployments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.tenancy.models.hierarchy import Tenant


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: int
    tenant_uuid: str
    tenant_slug: str
    deployment_mode: str

    def scope_filter(self, model: Any, column_name: str = "tenant_id") -> Any:
        column = getattr(model, column_name)
        return column == self.tenant_id


def resolve_default_tenant(db: Session, settings: Settings | None = None) -> Tenant:
    settings = settings or get_settings()
    tenant = db.execute(select(Tenant).where(Tenant.slug == "default")).scalar_one_or_none()
    if tenant is not None:
        return tenant
    tenant = Tenant(name="Default Organization", slug="default", deployment_mode=settings.deployment_mode)
    db.add(tenant)
    db.flush()
    return tenant


def resolve_tenant_context(
    db: Session,
    *,
    request: Request | None = None,
    user_tenant_id: int | None = None,
    settings: Settings | None = None,
) -> TenantContext:
    settings = settings or get_settings()

    if settings.deployment_mode == "dedicated":
        tenant = resolve_default_tenant(db, settings)
        return TenantContext(
            tenant_id=tenant.id,
            tenant_uuid=tenant.tenant_uuid,
            tenant_slug=tenant.slug,
            deployment_mode=settings.deployment_mode,
        )

    tenant_id = user_tenant_id
    if request is not None:
        header_tenant = request.headers.get("x-tenant-id")
        if header_tenant and header_tenant.isdigit():
            tenant_id = int(header_tenant)

    if tenant_id is None:
        tenant = resolve_default_tenant(db, settings)
    else:
        tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id, Tenant.active.is_(True))).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or inactive tenant.")

    return TenantContext(
        tenant_id=tenant.id,
        tenant_uuid=tenant.tenant_uuid,
        tenant_slug=tenant.slug,
        deployment_mode=settings.deployment_mode,
    )
