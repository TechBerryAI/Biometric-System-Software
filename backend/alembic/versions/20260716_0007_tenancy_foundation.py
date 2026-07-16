"""Multi-tenant hierarchy and tenant_id columns.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_uuid", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("deployment_mode", sa.String(16), server_default="saas", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("features", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("tenant_uuid"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("org_uuid", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_uuid"),
    )

    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("region_uuid", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_uuid"),
    )

    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("branch_uuid", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_uuid"),
    )

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("dept_uuid", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dept_uuid"),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("membership_uuid", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_uuid", sa.String(36), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("scope_json", JSONB, nullable=True),
        sa.Column("branch_ids", JSONB, nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_uuid"),
    )

    for table in ("employees", "devices", "attendance_logs", "device_commands", "users"):
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    conn = op.get_bind()
    default_uuid = str(uuid4())
    conn.execute(
        sa.text(
            """
            INSERT INTO tenants (tenant_uuid, name, slug, deployment_mode, active)
            VALUES (:uuid, 'Default Organization', 'default', 'saas', TRUE)
            """
        ),
        {"uuid": default_uuid},
    )
    conn.execute(sa.text("UPDATE employees SET tenant_id = 1 WHERE tenant_id IS NULL"))
    conn.execute(sa.text("UPDATE devices SET tenant_id = 1 WHERE tenant_id IS NULL"))
    conn.execute(sa.text("UPDATE attendance_logs SET tenant_id = 1 WHERE tenant_id IS NULL"))
    conn.execute(sa.text("UPDATE device_commands SET tenant_id = 1 WHERE tenant_id IS NULL"))
    conn.execute(sa.text("UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL"))


def downgrade() -> None:
    for table in ("users", "device_commands", "attendance_logs", "devices", "employees"):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
    op.drop_table("tenant_memberships")
    op.drop_table("departments")
    op.drop_table("branches")
    op.drop_table("regions")
    op.drop_table("organizations")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
