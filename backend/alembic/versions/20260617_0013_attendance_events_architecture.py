"""Attendance events, effective punches, and correction event tables with backfill.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_uuid", sa.String(length=36), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("employee_uuid", sa.String(length=36), nullable=True),
        sa.Column("device_mapping_id", sa.Integer(), nullable=True),
        sa.Column("punch_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="device_sync", nullable=False),
        sa.Column("sync_batch_uuid", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["device_mapping_id"], ["device_user_mappings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["employee_uuid"], ["employees.employee_uuid"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "employee_code", "timestamp", name="uq_event_device_employee_ts"),
        sa.UniqueConstraint("event_uuid", name="uq_attendance_event_uuid"),
    )
    op.create_index("ix_attendance_events_employee_code", "attendance_events", ["employee_code"])
    op.create_index("ix_attendance_events_timestamp", "attendance_events", ["timestamp"])
    op.create_index("ix_attendance_events_employee_uuid", "attendance_events", ["employee_uuid"])
    op.create_index("ix_attendance_events_sync_batch_uuid", "attendance_events", ["sync_batch_uuid"])

    op.create_table(
        "attendance_effective_punches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("punch_type", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="derived", nullable=False),
        sa.Column("correction_uuid", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_effective_punches_employee_date", "attendance_effective_punches", ["employee_id", "local_date"])
    op.create_index("ix_effective_punches_timestamp", "attendance_effective_punches", ["timestamp"])
    op.create_index("ix_effective_punches_active", "attendance_effective_punches", ["is_active"])
    op.create_index("ix_effective_punches_correction_uuid", "attendance_effective_punches", ["correction_uuid"])

    op.create_table(
        "attendance_correction_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_uuid", sa.String(length=36), nullable=False),
        sa.Column("correction_uuid", sa.String(length=36), nullable=False),
        sa.Column("device_operation_uuid", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_uuid", name="uq_correction_event_uuid"),
        sa.UniqueConstraint("device_operation_uuid", name="uq_correction_device_operation_uuid"),
    )
    op.create_index("ix_correction_events_correction_uuid", "attendance_correction_events", ["correction_uuid"])
    op.create_index("ix_correction_events_event_type", "attendance_correction_events", ["event_type"])

    op.add_column(
        "attendance_corrections",
        sa.Column("device_operation_uuid", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_attendance_corrections_device_operation_uuid",
        "attendance_corrections",
        ["device_operation_uuid"],
        unique=True,
    )

    op.execute(
        """
        INSERT INTO attendance_events (
            event_uuid, employee_code, timestamp, device_id, employee_uuid,
            device_mapping_id, punch_type, source, created_at
        )
        SELECT
            gen_random_uuid()::text,
            employee_code,
            timestamp,
            device_id,
            employee_uuid,
            device_mapping_id,
            punch_type,
            'backfill',
            COALESCE(created_at, timestamp)
        FROM attendance_logs
        ON CONFLICT (device_id, employee_code, timestamp) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_corrections_device_operation_uuid", table_name="attendance_corrections")
    op.drop_column("attendance_corrections", "device_operation_uuid")
    op.drop_index("ix_correction_events_event_type", table_name="attendance_correction_events")
    op.drop_index("ix_correction_events_correction_uuid", table_name="attendance_correction_events")
    op.drop_table("attendance_correction_events")
    op.drop_index("ix_effective_punches_correction_uuid", table_name="attendance_effective_punches")
    op.drop_index("ix_effective_punches_active", table_name="attendance_effective_punches")
    op.drop_index("ix_effective_punches_timestamp", table_name="attendance_effective_punches")
    op.drop_index("ix_effective_punches_employee_date", table_name="attendance_effective_punches")
    op.drop_table("attendance_effective_punches")
    op.drop_index("ix_attendance_events_sync_batch_uuid", table_name="attendance_events")
    op.drop_index("ix_attendance_events_employee_uuid", table_name="attendance_events")
    op.drop_index("ix_attendance_events_timestamp", table_name="attendance_events")
    op.drop_index("ix_attendance_events_employee_code", table_name="attendance_events")
    op.drop_table("attendance_events")
