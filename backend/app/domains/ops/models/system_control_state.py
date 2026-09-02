"""Global governance toggles for maintenance and emergency freeze."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemControlState(Base):
    __tablename__ = "system_control_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    singleton_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default="global", server_default="global")
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    emergency_freeze_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    changed_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
