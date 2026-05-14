"""Harden device command safety, verification, and firmware profiles.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_sync_events", sa.Column("event_source", sa.String(length=64), nullable=True))
    op.create_index("ix_device_sync_events_event_source", "device_sync_events", ["event_source"])

    op.add_column("device_commands", sa.Column("retry_backoff_seconds", sa.Integer(), server_default="0", nullable=False))
    op.add_column("device_commands", sa.Column("initiated_by", sa.String(length=36), nullable=True))
    op.add_column("device_commands", sa.Column("initiated_from", sa.String(length=64), nullable=True))
    op.add_column("device_commands", sa.Column("verification_status", sa.String(length=32), nullable=True))
    op.add_column("device_commands", sa.Column("verification_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("device_commands", sa.Column("firmware_profile", sa.String(length=128), nullable=True))
    op.add_column("device_commands", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE device_commands SET initiated_by = created_by WHERE initiated_by IS NULL")
    op.drop_index("ix_device_commands_created_by", table_name="device_commands")
    op.drop_column("device_commands", "created_by")
    op.create_index("ix_device_commands_initiated_by", "device_commands", ["initiated_by"])
    op.create_index("ix_device_commands_verification_status", "device_commands", ["verification_status"])
    op.create_index("ix_device_commands_heartbeat_at", "device_commands", ["heartbeat_at"])

    op.create_table(
        "verification_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("command_id", sa.Integer(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("expected_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actual_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mismatch_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["command_id"], ["device_commands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_results_command_id", "verification_results", ["command_id"])
    op.create_index("ix_verification_results_verification_status", "verification_results", ["verification_status"])
    op.create_index("ix_verification_results_verified_at", "verification_results", ["verified_at"])

    op.create_table(
        "device_firmware_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("firmware_version", sa.String(length=128), nullable=False),
        sa.Column("supports_user_write", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_name_update", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_uid_update", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_card_update", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("safe_write_strategy", sa.String(length=64), nullable=False),
        sa.Column("reconnect_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("write_delay_ms", sa.Integer(), server_default="500", nullable=False),
        sa.Column("verification_strategy", sa.String(length=64), nullable=False),
        sa.Column("known_limitations", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firmware_version"),
    )
    op.create_index("ix_device_firmware_profiles_firmware_version", "device_firmware_profiles", ["firmware_version"])

    op.create_table(
        "reconciliation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconciliation_jobs_job_type", "reconciliation_jobs", ["job_type"])
    op.create_index("ix_reconciliation_jobs_target_entity", "reconciliation_jobs", ["target_entity"])
    op.create_index("ix_reconciliation_jobs_status", "reconciliation_jobs", ["status"])
    op.create_index("ix_reconciliation_jobs_correlation_id", "reconciliation_jobs", ["correlation_id"])
    op.create_index("ix_reconciliation_jobs_created_at", "reconciliation_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_device_sync_events_event_source", table_name="device_sync_events")
    op.drop_column("device_sync_events", "event_source")

    op.drop_index("ix_reconciliation_jobs_created_at", table_name="reconciliation_jobs")
    op.drop_index("ix_reconciliation_jobs_correlation_id", table_name="reconciliation_jobs")
    op.drop_index("ix_reconciliation_jobs_status", table_name="reconciliation_jobs")
    op.drop_index("ix_reconciliation_jobs_target_entity", table_name="reconciliation_jobs")
    op.drop_index("ix_reconciliation_jobs_job_type", table_name="reconciliation_jobs")
    op.drop_table("reconciliation_jobs")

    op.drop_index("ix_device_firmware_profiles_firmware_version", table_name="device_firmware_profiles")
    op.drop_table("device_firmware_profiles")

    op.drop_index("ix_verification_results_verified_at", table_name="verification_results")
    op.drop_index("ix_verification_results_verification_status", table_name="verification_results")
    op.drop_index("ix_verification_results_command_id", table_name="verification_results")
    op.drop_table("verification_results")

    op.drop_index("ix_device_commands_heartbeat_at", table_name="device_commands")
    op.drop_index("ix_device_commands_verification_status", table_name="device_commands")
    op.drop_index("ix_device_commands_initiated_by", table_name="device_commands")
    op.add_column("device_commands", sa.Column("created_by", sa.String(length=36), nullable=True))
    op.create_index("ix_device_commands_created_by", "device_commands", ["created_by"])
    op.execute("UPDATE device_commands SET created_by = initiated_by WHERE created_by IS NULL")
    op.drop_column("device_commands", "heartbeat_at")
    op.drop_column("device_commands", "firmware_profile")
    op.drop_column("device_commands", "verification_details")
    op.drop_column("device_commands", "verification_status")
    op.drop_column("device_commands", "initiated_from")
    op.drop_column("device_commands", "initiated_by")
    op.drop_column("device_commands", "retry_backoff_seconds")
