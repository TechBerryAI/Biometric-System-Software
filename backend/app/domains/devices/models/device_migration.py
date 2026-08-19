"""Replacement-device metadata migration runs and per-employee items."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DeviceMigration(Base):
    __tablename__ = "device_migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    migration_uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid4())
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PREFLIGHT", server_default="PREFLIGHT", index=True)
    include_departed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    target_ip: Mapped[str] = mapped_column(String(128), nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False, default=4370)
    inspect_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preflight_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["DeviceMigrationItem"]] = relationship(
        "DeviceMigrationItem",
        back_populates="migration",
        cascade="all, delete-orphan",
    )


class DeviceMigrationItem(Base):
    __tablename__ = "device_migration_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    migration_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("device_migrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    employee_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card: Mapped[str | None] = mapped_column(String(128), nullable=True)
    planned_action: Mapped[str] = mapped_column(String(16), nullable=False)
    actual_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conflict_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    command_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    verification_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    migration: Mapped[DeviceMigration] = relationship("DeviceMigration", back_populates="items")
