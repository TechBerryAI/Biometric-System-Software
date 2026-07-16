"""Persisted device-vs-mapping drift events from reconciliation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceUserDrift(Base):
    __tablename__ = "device_user_drift"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    drift_type: Mapped[str] = mapped_column(String(32), nullable=False)
    employee_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", server_default="open", index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(64), nullable=True)
    command_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
