"""Replay-safe execution history for queued device commands."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CommandExecutionHistory(Base):
    __tablename__ = "command_execution_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command_id: Mapped[int] = mapped_column(ForeignKey("device_commands.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    verification_result: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    final_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="RUNNING", server_default="RUNNING")
