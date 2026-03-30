"""add device metadata fields to employees

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-30 22:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("device_uid", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("device_privilege", sa.Integer(), nullable=True))
    op.add_column("employees", sa.Column("device_group_id", sa.String(length=64), nullable=True))
    op.add_column("employees", sa.Column("device_card", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "device_card")
    op.drop_column("employees", "device_group_id")
    op.drop_column("employees", "device_privilege")
    op.drop_column("employees", "device_uid")

