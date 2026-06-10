"""Firmware capabilities and safe-write policies per version fingerprint."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceFirmwareProfile(Base):
    __tablename__ = "device_firmware_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firmware_version: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    supports_user_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    supports_name_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    supports_uid_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    supports_card_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    safe_write_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="upsert_then_readback")
    reconnect_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    write_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=500, server_default="500")
    verification_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="readback_get_users")
    known_limitations: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    supports_attlog_delete_by_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    supports_attlog_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    attlog_record_size: Mapped[int] = mapped_column(Integer, nullable=False, default=40, server_default="40")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
