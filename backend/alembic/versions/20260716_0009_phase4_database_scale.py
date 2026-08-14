"""Phase 4 database scale: indexes, idempotency_keys, archive metadata, drift.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-16

PostgreSQL partitioning notes for attendance_logs (apply manually in production):

  -- Convert to range-partitioned parent (zero-downtime cutover recommended via
  -- new table + dual-write, then swap). Example monthly partitions:
  --
  -- CREATE TABLE attendance_logs_partitioned (
  --   LIKE attendance_logs INCLUDING ALL
  -- ) PARTITION BY RANGE (timestamp);
  --
  -- CREATE TABLE attendance_logs_y2026m01 PARTITION OF attendance_logs_partitioned
  --   FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
  --
  -- Detach old partitions for archival:
  -- ALTER TABLE attendance_logs_partitioned DETACH PARTITION attendance_logs_y2025m01;
  --
  -- Archive job (app.domains.attendance.services.archive_service) records
  -- detach/export metadata in attendance_archive_runs.

This migration adds composite indexes safe for both partitioned and
non-partitioned layouts, plus supporting metadata tables.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite indexes for common attendance query patterns.
    op.create_index(
        "ix_attendance_logs_device_ts",
        "attendance_logs",
        ["device_id", "timestamp"],
    )
    op.create_index(
        "ix_attendance_logs_employee_ts",
        "attendance_logs",
        ["employee_code", "timestamp"],
    )
    op.create_index(
        "ix_attendance_logs_tenant_ts",
        "attendance_logs",
        ["tenant_id", "timestamp"],
    )
    op.create_index(
        "ix_attendance_logs_punch_ts",
        "attendance_logs",
        ["punch_type", "timestamp"],
    )

    # Cross-service idempotency for webhook / sync / command callers.
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("response_json", JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    # Archive run metadata (partition detach / export tracking).
    op.create_table(
        "attendance_archive_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_uuid", sa.String(36), nullable=False),
        sa.Column("partition_name", sa.String(128), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_uri", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("detail", sa.String(2000), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_uuid"),
    )
    op.create_index("ix_attendance_archive_runs_status", "attendance_archive_runs", ["status"])
    op.create_index("ix_attendance_archive_runs_period", "attendance_archive_runs", ["period_start", "period_end"])

    # Device user drift persistence for reconciliation.
    op.create_table(
        "device_user_drift",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("device_user_id", sa.String(64), nullable=False),
        sa.Column("drift_type", sa.String(32), nullable=False),
        sa.Column("employee_uuid", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(64), nullable=True),
        sa.Column("command_uuid", sa.String(36), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_user_drift_device_id", "device_user_drift", ["device_id"])
    op.create_index("ix_device_user_drift_status", "device_user_drift", ["status"])
    op.create_index(
        "ix_device_user_drift_open",
        "device_user_drift",
        ["device_id", "device_user_id", "drift_type"],
        unique=False,
    )

    # Extend device_commands audit trail.
    op.add_column("device_commands", sa.Column("audit_event_uuid", sa.String(36), nullable=True))
    op.add_column(
        "device_commands",
        sa.Column("status_history", JSONB, nullable=True),
    )
    op.create_index("ix_device_commands_audit_event_uuid", "device_commands", ["audit_event_uuid"])


def downgrade() -> None:
    op.drop_index("ix_device_commands_audit_event_uuid", table_name="device_commands")
    op.drop_column("device_commands", "status_history")
    op.drop_column("device_commands", "audit_event_uuid")

    op.drop_index("ix_device_user_drift_open", table_name="device_user_drift")
    op.drop_index("ix_device_user_drift_status", table_name="device_user_drift")
    op.drop_index("ix_device_user_drift_device_id", table_name="device_user_drift")
    op.drop_table("device_user_drift")

    op.drop_index("ix_attendance_archive_runs_period", table_name="attendance_archive_runs")
    op.drop_index("ix_attendance_archive_runs_status", table_name="attendance_archive_runs")
    op.drop_table("attendance_archive_runs")

    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_tenant_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_attendance_logs_punch_ts", table_name="attendance_logs")
    op.drop_index("ix_attendance_logs_tenant_ts", table_name="attendance_logs")
    op.drop_index("ix_attendance_logs_employee_ts", table_name="attendance_logs")
    op.drop_index("ix_attendance_logs_device_ts", table_name="attendance_logs")
