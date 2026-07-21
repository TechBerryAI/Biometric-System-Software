"""Widen attendance_logs unique key to include punch_type.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-21

Allows distinct check directions at the same second on the same device
(e.g. In then Out) while still ignoring exact sync replays.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_log_device_employee_ts", "attendance_logs", type_="unique")
    op.create_unique_constraint(
        "uq_log_device_employee_ts_punch",
        "attendance_logs",
        ["device_id", "employee_code", "timestamp", "punch_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_log_device_employee_ts_punch", "attendance_logs", type_="unique")
    op.create_unique_constraint(
        "uq_log_device_employee_ts",
        "attendance_logs",
        ["device_id", "employee_code", "timestamp"],
    )
