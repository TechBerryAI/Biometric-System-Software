"""Skip list for repaired device punch timestamps.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_ingest_skips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("punch_type", sa.String(length=32), nullable=False),
        sa.Column("repaired_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id",
            "employee_code",
            "timestamp",
            "punch_type",
            name="uq_ingest_skip_device_employee_ts_punch",
        ),
    )
    op.create_index("ix_attendance_ingest_skips_device_id", "attendance_ingest_skips", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_attendance_ingest_skips_device_id", table_name="attendance_ingest_skips")
    op.drop_table("attendance_ingest_skips")
