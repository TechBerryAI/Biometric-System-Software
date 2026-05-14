"""Rolling runtime health/risk scores for each device."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceRuntimeHealth(Base):
    __tablename__ = "device_runtime_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    connection_stability_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    timeout_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reconnect_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    protocol_error_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    verification_failure_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    drift_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    operational_risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW", server_default="LOW", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
