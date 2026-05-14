"""Add attendance_anomalies table for deterministic AI anomaly outputs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_anomalies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("anomaly_key", sa.String(length=128), nullable=False),
        sa.Column("anomaly_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=True),
        sa.Column("recommendation", sa.String(length=1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anomaly_key", "anomaly_date", name="uq_attendance_anomaly_key_date"),
    )
    op.create_index("ix_attendance_anomalies_anomaly_key", "attendance_anomalies", ["anomaly_key"])
    op.create_index("ix_attendance_anomalies_anomaly_date", "attendance_anomalies", ["anomaly_date"])
    op.create_index("ix_attendance_anomalies_category", "attendance_anomalies", ["category"])
    op.create_index("ix_attendance_anomalies_department", "attendance_anomalies", ["department"])


def downgrade() -> None:
    op.drop_index("ix_attendance_anomalies_department", table_name="attendance_anomalies")
    op.drop_index("ix_attendance_anomalies_category", table_name="attendance_anomalies")
    op.drop_index("ix_attendance_anomalies_anomaly_date", table_name="attendance_anomalies")
    op.drop_index("ix_attendance_anomalies_anomaly_key", table_name="attendance_anomalies")
    op.drop_table("attendance_anomalies")

