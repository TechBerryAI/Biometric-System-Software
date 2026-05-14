"""Aggregated fleet/site health snapshots for operations center."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FleetHealthMetric(Base):
    __tablename__ = "fleet_health_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="GLOBAL", server_default="GLOBAL")
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True, default="global", server_default="global")
    office_health: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    regional_health: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    failing_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    drift_hotspots: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    firmware_risk_distribution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    queue_pressure: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reconciliation_backlog: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
