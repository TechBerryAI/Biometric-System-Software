"""Add replay history, snapshots, and operation safety matrix.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_execution_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("command_id", sa.Integer(), nullable=False),
        sa.Column("execution_attempt", sa.Integer(), nullable=False),
        sa.Column("execution_hash", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("verification_result", sa.String(length=32), nullable=True),
        sa.Column("final_status", sa.String(length=32), server_default="RUNNING", nullable=False),
        sa.ForeignKeyConstraint(["command_id"], ["device_commands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", "execution_attempt", name="uq_execution_history_command_attempt"),
    )
    op.create_index("ix_command_execution_history_command_id", "command_execution_history", ["command_id"])
    op.create_index("ix_command_execution_history_execution_hash", "command_execution_history", ["execution_hash"])
    op.create_index("ix_command_execution_history_started_at", "command_execution_history", ["started_at"])
    op.create_index("ix_command_execution_history_worker_id", "command_execution_history", ["worker_id"])
    op.create_index("ix_command_execution_history_verification_result", "command_execution_history", ["verification_result"])
    op.create_index("ix_command_execution_history_final_status", "command_execution_history", ["final_status"])

    op.create_table(
        "device_state_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column("user_count", sa.Integer(), nullable=False),
        sa.Column("user_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("firmware_version", sa.String(length=128), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_state_snapshots_device_id", "device_state_snapshots", ["device_id"])
    op.create_index("ix_device_state_snapshots_snapshot_type", "device_state_snapshots", ["snapshot_type"])
    op.create_index("ix_device_state_snapshots_snapshot_hash", "device_state_snapshots", ["snapshot_hash"])
    op.create_index("ix_device_state_snapshots_firmware_version", "device_state_snapshots", ["firmware_version"])
    op.create_index("ix_device_state_snapshots_captured_at", "device_state_snapshots", ["captured_at"])

    op.create_table(
        "operation_safety_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("firmware_compatibility", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risk_level", sa.String(length=16), server_default="SAFE", nullable=False),
        sa.Column("verification_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("rollback_possible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("retry_safe", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("requires_manual_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_type"),
    )
    op.create_index("ix_operation_safety_profiles_operation_type", "operation_safety_profiles", ["operation_type"])

    op.execute(
        """
        INSERT INTO operation_safety_profiles (
            operation_type, firmware_compatibility, risk_level, verification_required,
            rollback_possible, retry_safe, requires_manual_review
        ) VALUES (
            'UPSERT_USER',
            '{"supported": ["*"]}'::jsonb,
            'MODERATE',
            true,
            false,
            true,
            false
        )
        ON CONFLICT (operation_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_operation_safety_profiles_operation_type", table_name="operation_safety_profiles")
    op.drop_table("operation_safety_profiles")

    op.drop_index("ix_device_state_snapshots_captured_at", table_name="device_state_snapshots")
    op.drop_index("ix_device_state_snapshots_firmware_version", table_name="device_state_snapshots")
    op.drop_index("ix_device_state_snapshots_snapshot_hash", table_name="device_state_snapshots")
    op.drop_index("ix_device_state_snapshots_snapshot_type", table_name="device_state_snapshots")
    op.drop_index("ix_device_state_snapshots_device_id", table_name="device_state_snapshots")
    op.drop_table("device_state_snapshots")

    op.drop_index("ix_command_execution_history_final_status", table_name="command_execution_history")
    op.drop_index("ix_command_execution_history_verification_result", table_name="command_execution_history")
    op.drop_index("ix_command_execution_history_worker_id", table_name="command_execution_history")
    op.drop_index("ix_command_execution_history_started_at", table_name="command_execution_history")
    op.drop_index("ix_command_execution_history_execution_hash", table_name="command_execution_history")
    op.drop_index("ix_command_execution_history_command_id", table_name="command_execution_history")
    op.drop_table("command_execution_history")
