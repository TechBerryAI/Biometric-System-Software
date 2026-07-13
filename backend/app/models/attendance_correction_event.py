"""Append-only correction workflow events for internal forensic access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceCorrectionEvent(Base):
    __tablename__ = "attendance_correction_events"
    __table_args__ = (
        UniqueConstraint("event_uuid", name="uq_correction_event_uuid"),
        UniqueConstraint("device_operation_uuid", name="uq_correction_device_operation_uuid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    correction_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_operation_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
