"""Device metadata migration tables for replacement-hardware cutover.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_migrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("migration_uuid", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PREFLIGHT"),
        sa.Column("include_departed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("target_ip", sa.String(length=128), nullable=False),
        sa.Column("target_port", sa.Integer(), nullable=False, server_default="4370"),
        sa.Column("inspect_snapshot", JSONB, nullable=True),
        sa.Column("preflight_summary", JSONB, nullable=True),
        sa.Column("report", JSONB, nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("migration_uuid"),
    )
    op.create_index("ix_device_migrations_tenant_id", "device_migrations", ["tenant_id"])
    op.create_index("ix_device_migrations_migration_uuid", "device_migrations", ["migration_uuid"])
    op.create_index("ix_device_migrations_device_id", "device_migrations", ["device_id"])
    op.create_index("ix_device_migrations_status", "device_migrations", ["status"])
    op.create_index("ix_device_migrations_created_by", "device_migrations", ["created_by"])
    op.create_index("ix_device_migrations_created_at", "device_migrations", ["created_at"])

    op.create_table(
        "device_migration_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("migration_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("employee_uuid", sa.String(length=36), nullable=False),
        sa.Column("device_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("planned_uid", sa.Integer(), nullable=True),
        sa.Column("assigned_uid", sa.Integer(), nullable=True),
        sa.Column("card", sa.String(length=128), nullable=True),
        sa.Column("planned_action", sa.String(length=16), nullable=False),
        sa.Column("actual_action", sa.String(length=16), nullable=True),
        sa.Column("conflict_reason", sa.String(length=500), nullable=True),
        sa.Column("command_uuid", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("verification_details", JSONB, nullable=True),
        sa.ForeignKeyConstraint(["migration_id"], ["device_migrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_migration_items_migration_id", "device_migration_items", ["migration_id"])
    op.create_index("ix_device_migration_items_employee_id", "device_migration_items", ["employee_id"])
    op.create_index("ix_device_migration_items_employee_uuid", "device_migration_items", ["employee_uuid"])
    op.create_index("ix_device_migration_items_device_user_id", "device_migration_items", ["device_user_id"])


def downgrade() -> None:
    op.drop_index("ix_device_migration_items_device_user_id", table_name="device_migration_items")
    op.drop_index("ix_device_migration_items_employee_uuid", table_name="device_migration_items")
    op.drop_index("ix_device_migration_items_employee_id", table_name="device_migration_items")
    op.drop_index("ix_device_migration_items_migration_id", table_name="device_migration_items")
    op.drop_table("device_migration_items")
    op.drop_index("ix_device_migrations_created_at", table_name="device_migrations")
    op.drop_index("ix_device_migrations_created_by", table_name="device_migrations")
    op.drop_index("ix_device_migrations_status", table_name="device_migrations")
    op.drop_index("ix_device_migrations_device_id", table_name="device_migrations")
    op.drop_index("ix_device_migrations_migration_uuid", table_name="device_migrations")
    op.drop_index("ix_device_migrations_tenant_id", table_name="device_migrations")
    op.drop_table("device_migrations")
