"""Employee ORM model (device_user_id is the authoritative device identity)."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import DateTime, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Device identity from ZKTeco user.user_id (can be alphanumeric like TBC209)
    device_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_privilege: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_card: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shift_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    shift_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    sessions = relationship("AttendanceSession", back_populates="employee")
