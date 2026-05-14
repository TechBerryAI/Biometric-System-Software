"""Enterprise firmware certification catalog."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CertifiedFirmwareProfile(Base):
    __tablename__ = "certified_firmware_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firmware_version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    device_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    certification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNCERTIFIED", server_default="UNCERTIFIED", index=True)
    supported_operations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    unsafe_operations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reconnect_requirements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    known_bugs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    write_stability_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
    verification_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="strict_readback", server_default="strict_readback")
    rollout_recommendation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    operational_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
