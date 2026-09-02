"""Attendance punches from the biometric device (single source of truth)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "employee_code",
            "timestamp",
            "punch_type",
            name="uq_log_device_employee_ts_punch",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    employee_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    employee_uuid: Mapped[str | None] = mapped_column(
        String(40),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
