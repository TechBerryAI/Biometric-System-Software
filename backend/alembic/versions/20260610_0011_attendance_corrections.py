"""Add attendance corrections and sync suppressions for GOD-mode edits.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("correction_uuid", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("previous_check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_user_uuid", sa.String(length=36), nullable=True),
        sa.Column("device_command_uuid", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correction_uuid"),
    )
    op.create_index("ix_attendance_corrections_employee_id", "attendance_corrections", ["employee_id"])
    op.create_index("ix_attendance_corrections_local_date", "attendance_corrections", ["local_date"])
    op.create_index("ix_attendance_corrections_actor_user_uuid", "attendance_corrections", ["actor_user_uuid"])
    op.create_index("ix_attendance_corrections_device_command_uuid", "attendance_corrections", ["device_command_uuid"])

    op.create_table(
        "attendance_sync_suppressions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("suppressed_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=32), server_default="correction", nullable=False),
        sa.Column("correction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["correction_id"], ["attendance_corrections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id",
            "employee_code",
            "suppressed_timestamp",
            name="uq_suppression_device_employee_ts",
        ),
    )
    op.create_index("ix_attendance_sync_suppressions_device_id", "attendance_sync_suppressions", ["device_id"])
    op.create_index("ix_attendance_sync_suppressions_employee_code", "attendance_sync_suppressions", ["employee_code"])
    op.create_index(
        "ix_attendance_sync_suppressions_suppressed_timestamp",
        "attendance_sync_suppressions",
        ["suppressed_timestamp"],
    )

    op.add_column(
        "device_firmware_profiles",
        sa.Column("supports_attlog_delete_by_time", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "device_firmware_profiles",
        sa.Column("supports_attlog_write", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "device_firmware_profiles",
        sa.Column("attlog_record_size", sa.Integer(), server_default="40", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("device_firmware_profiles", "attlog_record_size")
    op.drop_column("device_firmware_profiles", "supports_attlog_write")
    op.drop_column("device_firmware_profiles", "supports_attlog_delete_by_time")
    op.drop_table("attendance_sync_suppressions")
    op.drop_table("attendance_corrections")
