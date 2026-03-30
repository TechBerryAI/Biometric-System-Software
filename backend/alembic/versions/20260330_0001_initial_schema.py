"""Initial schema: employees, attendance_logs, attendance_sessions.

Revision ID: 0001
Revises:
Create Date: 2026-03-30

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("shift_start", sa.Time(), nullable=True),
        sa.Column("shift_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_user_id"),
    )
    op.create_index(op.f("ix_employees_device_user_id"), "employees", ["device_user_id"], unique=False)

    op.create_table(
        "attendance_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("punch_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code", "timestamp", name="uq_log_employee_ts"),
    )
    op.create_index(op.f("ix_attendance_logs_employee_code"), "attendance_logs", ["employee_code"], unique=False)
    op.create_index(op.f("ix_attendance_logs_timestamp"), "attendance_logs", ["timestamp"], unique=False)

    op.create_table(
        "attendance_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("check_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("work_duration", sa.Integer(), nullable=True),
        sa.Column("late_minutes", sa.Integer(), nullable=True),
        sa.Column("early_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attendance_sessions_check_in"), "attendance_sessions", ["check_in"], unique=False)
    op.create_index(op.f("ix_attendance_sessions_employee_id"), "attendance_sessions", ["employee_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_attendance_sessions_employee_id"), table_name="attendance_sessions")
    op.drop_index(op.f("ix_attendance_sessions_check_in"), table_name="attendance_sessions")
    op.drop_table("attendance_sessions")
    op.drop_index(op.f("ix_attendance_logs_timestamp"), table_name="attendance_logs")
    op.drop_index(op.f("ix_attendance_logs_employee_code"), table_name="attendance_logs")
    op.drop_table("attendance_logs")
    op.drop_index(op.f("ix_employees_device_user_id"), table_name="employees")
    op.drop_table("employees")
