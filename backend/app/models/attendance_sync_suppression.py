"""Prevent re-import of superseded device punch timestamps after attendance adjustments."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceSyncSuppression(Base):
    __tablename__ = "attendance_sync_suppressions"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "employee_code",
            "suppressed_timestamp",
            name="uq_suppression_device_employee_ts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    suppressed_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="correction", server_default="correction")
    correction_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("attendance_corrections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
