"""Registered biometric devices for orchestration and health tracking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.ids import new_device_id


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    device_uuid: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True, default=new_device_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(128), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=4370)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    firmware_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL", server_default="NORMAL", index=True)
    quarantine_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    branch_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    connectivity_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pull", server_default="pull", index=True
    )
    offline_buffer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    device_secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
