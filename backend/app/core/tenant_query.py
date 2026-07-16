"""Tenant-scoped query helpers."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.tenant_context import TenantContext

T = TypeVar("T")


def tenant_scoped_select(model: type[T], ctx: TenantContext) -> Select[tuple[T]]:
    if hasattr(model, "tenant_id"):
        return select(model).where(model.tenant_id == ctx.tenant_id)  # type: ignore[attr-defined]
    return select(model)


def apply_tenant_scope(stmt: Select[Any], ctx: TenantContext, model: Any) -> Select[Any]:
    if hasattr(model, "tenant_id"):
        return stmt.where(model.tenant_id == ctx.tenant_id)  # type: ignore[attr-defined]
    return stmt


def get_tenant_or_403(db: Session, ctx: TenantContext, model: type[T], entity_id: int) -> T | None:
    row = db.execute(
        select(model).where(model.id == entity_id, model.tenant_id == ctx.tenant_id)  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    return row
