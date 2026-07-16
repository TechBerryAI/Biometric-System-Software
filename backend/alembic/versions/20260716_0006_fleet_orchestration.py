"""Fleet orchestration: device sync state and fleet metadata columns.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("branch_id", sa.String(128), nullable=True))
    op.add_column(
        "devices",
        sa.Column("connectivity_mode", sa.String(16), nullable=False, server_default="pull"),
    )
    op.add_column("devices", sa.Column("offline_buffer", JSONB, nullable=True))
    op.add_column("devices", sa.Column("device_secret_hash", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("config_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_devices_branch_id", "devices", ["branch_id"])
    op.create_index("ix_devices_connectivity_mode", "devices", ["connectivity_mode"])

    op.create_table(
        "device_sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("last_user_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attendance_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attendance_cursor", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_counts", JSONB, nullable=True),
        sa.Column("conflict_resolution", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_device_sync_state_device_id", "device_sync_state", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_device_sync_state_device_id", table_name="device_sync_state")
    op.drop_table("device_sync_state")
    op.drop_index("ix_devices_connectivity_mode", table_name="devices")
    op.drop_index("ix_devices_branch_id", table_name="devices")
    op.drop_column("devices", "config_version")
    op.drop_column("devices", "device_secret_hash")
    op.drop_column("devices", "offline_buffer")
    op.drop_column("devices", "connectivity_mode")
    op.drop_column("devices", "branch_id")
