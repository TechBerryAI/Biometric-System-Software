"""Widen device_operation_uuid for composite idempotency keys.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE attendance_correction_events
        ALTER COLUMN device_operation_uuid TYPE VARCHAR(128)
        """
    )
    op.execute(
        """
        ALTER TABLE attendance_corrections
        ALTER COLUMN device_operation_uuid TYPE VARCHAR(128)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE attendance_corrections
        ALTER COLUMN device_operation_uuid TYPE VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE attendance_correction_events
        ALTER COLUMN device_operation_uuid TYPE VARCHAR(36)
        """
    )
