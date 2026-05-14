"""Operator approval workflow records for high-risk actions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperatorApproval(Base):
    __tablename__ = "operator_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    approval_uuid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_entity: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING", index=True)
    requires_dual_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    request_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approval_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
