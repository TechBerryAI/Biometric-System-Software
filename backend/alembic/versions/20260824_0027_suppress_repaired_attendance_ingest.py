"""Block re-insert of repaired original device timestamps.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-24

The live Celery worker may still run ingest code from before the skip list.
A BEFORE INSERT trigger enforces attendance_ingest_skips at the database so
full pulls cannot restore Sunday-night AM/PM stamps after a +12h repair.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION suppress_repaired_attendance_ingest()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM attendance_ingest_skips s
            WHERE s.device_id = NEW.device_id
              AND s.employee_code = NEW.employee_code
              AND s.timestamp = NEW.timestamp
              AND s.punch_type = NEW.punch_type
          ) THEN
            RETURN NULL;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_suppress_repaired_attendance_ingest
        BEFORE INSERT ON attendance_logs
        FOR EACH ROW
        EXECUTE FUNCTION suppress_repaired_attendance_ingest();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_suppress_repaired_attendance_ingest ON attendance_logs")
    op.execute("DROP FUNCTION IF EXISTS suppress_repaired_attendance_ingest()")
