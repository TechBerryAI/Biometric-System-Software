"""User tenant membership and scoped roles."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.ids import new_membership_id


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_uuid: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, default=new_membership_id)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_uuid: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    branch_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
