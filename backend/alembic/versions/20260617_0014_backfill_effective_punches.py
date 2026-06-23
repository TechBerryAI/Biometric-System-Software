"""Backfill effective punches from attendance events.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Effective punches are derived at runtime; seed from events for employees with mappings.
    op.execute(
        """
        INSERT INTO attendance_effective_punches (
            employee_id, local_date, punch_type, timestamp, source, is_active, created_at
        )
        SELECT DISTINCT ON (e.id, ae.timestamp, ae.punch_type)
            e.id,
            (ae.timestamp AT TIME ZONE 'UTC')::date,
            ae.punch_type,
            ae.timestamp,
            'backfill',
            true,
            ae.created_at
        FROM attendance_events ae
        JOIN employees e ON e.device_user_id = ae.employee_code
           OR (ae.employee_uuid IS NOT NULL AND e.employee_uuid = ae.employee_uuid)
        WHERE NOT EXISTS (
            SELECT 1 FROM attendance_sync_suppressions s
            WHERE s.device_id = ae.device_id
              AND s.employee_code = ae.employee_code
              AND abs(extract(epoch from (s.suppressed_timestamp - ae.timestamp))) <= 2
        )
        ORDER BY e.id, ae.timestamp, ae.punch_type, ae.id
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM attendance_effective_punches WHERE source = 'backfill'")
