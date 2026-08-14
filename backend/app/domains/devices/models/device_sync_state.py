"""Per-device sync cursor and conflict resolution state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceSyncState(Base):
    __tablename__ = "device_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    last_user_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attendance_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attendance_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    drift_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    conflict_resolution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
