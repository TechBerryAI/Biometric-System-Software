"""Detected attendance anomalies (stored separately from attendance facts)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceAnomaly(Base):
    __tablename__ = "attendance_anomalies"
    __table_args__ = (
        UniqueConstraint("anomaly_key", "anomaly_date", name="uq_attendance_anomaly_key_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anomaly_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    anomaly_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(String(600), nullable=False)
    explanation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

