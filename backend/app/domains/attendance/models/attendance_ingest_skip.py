"""Device punch stamps that must not be re-imported after a timestamp repair."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceIngestSkip(Base):
    __tablename__ = "attendance_ingest_skips"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "employee_code",
            "timestamp",
            "punch_type",
            name="uq_ingest_skip_device_employee_ts_punch",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_code: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    punch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    repaired_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
