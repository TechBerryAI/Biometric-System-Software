"""Safety classification and policy per device operation type."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperationSafetyProfile(Base):
    __tablename__ = "operation_safety_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    firmware_compatibility: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="SAFE", server_default="SAFE")
    verification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    rollback_possible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    retry_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
