"""Periodic and command-scoped snapshots of device state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceStateSnapshot(Base):
    __tablename__ = "device_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_count: Mapped[int] = mapped_column(Integer, nullable=False)
    user_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
