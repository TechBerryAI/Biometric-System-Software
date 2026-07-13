"""Attendance correction strict-mode fields and CORRECT_ATTENDANCE safety profile.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_corrections",
        sa.Column("device_tier", sa.String(length=1), nullable=True),
    )
    op.add_column(
        "attendance_corrections",
        sa.Column("device_verification_details", JSONB, nullable=True),
    )
    op.add_column(
        "attendance_corrections",
        sa.Column("correction_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "attendance_corrections",
        sa.Column("reimport_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_attendance_corrections_employee_date_status",
        "attendance_corrections",
        ["employee_id", "local_date", "status"],
    )

    op.execute(
        """
        INSERT INTO operation_safety_profiles (
            operation_type, firmware_compatibility, risk_level, verification_required,
            rollback_possible, retry_safe, requires_manual_review
        ) VALUES (
            'CORRECT_ATTENDANCE',
            '{"supported": ["tier_a"]}'::jsonb,
            'HIGH',
            true,
            false,
            true,
            true
        )
        ON CONFLICT (operation_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM operation_safety_profiles WHERE operation_type = 'CORRECT_ATTENDANCE'")
    op.drop_index("ix_attendance_corrections_employee_date_status", table_name="attendance_corrections")
    op.drop_column("attendance_corrections", "reimport_completed_at")
    op.drop_column("attendance_corrections", "correction_mode")
    op.drop_column("attendance_corrections", "device_verification_details")
    op.drop_column("attendance_corrections", "device_tier")
