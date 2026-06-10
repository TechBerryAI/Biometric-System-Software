"""GOD-mode attendance correction ledger (internal, not exposed in normal attendance APIs)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttendanceCorrection(Base):
    __tablename__ = "attendance_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correction_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    previous_check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor_user_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    device_command_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
