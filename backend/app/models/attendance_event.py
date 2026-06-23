"""Append-only raw attendance punches from biometric devices."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("device_id", "employee_code", "timestamp", name="uq_event_device_employee_ts"),
        UniqueConstraint("event_uuid", name="uq_attendance_event_uuid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    employee_uuid: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("employees.employee_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_mapping_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("device_user_mappings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    punch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="device_sync", server_default="device_sync")
    sync_batch_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
