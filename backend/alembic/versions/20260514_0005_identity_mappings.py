"""Introduce immutable employee identity and device user mappings.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.add_column("employees", sa.Column("employee_uuid", sa.String(length=36), nullable=True))
    op.execute("UPDATE employees SET employee_uuid = gen_random_uuid()::text WHERE employee_uuid IS NULL")
    op.alter_column("employees", "employee_uuid", nullable=False)
    op.create_index("ix_employees_employee_uuid", "employees", ["employee_uuid"], unique=True)

    op.create_table(
        "device_user_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_uuid", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("device_user_id", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_uuid"],
            ["employees.employee_uuid"],
            name="fk_device_user_mappings_employee_uuid_employees",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_user_mappings_employee_uuid", "device_user_mappings", ["employee_uuid"])
    op.create_index("ix_device_user_mappings_device_id", "device_user_mappings", ["device_id"])
    op.create_index("ix_device_user_mappings_device_user_id", "device_user_mappings", ["device_user_id"])
    op.create_index(
        "uq_active_mapping_per_device_identity",
        "device_user_mappings",
        ["device_id", "device_user_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )
    op.create_index(
        "uq_active_mapping_per_employee_device",
        "device_user_mappings",
        ["employee_uuid", "device_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )

    op.add_column("attendance_logs", sa.Column("employee_uuid", sa.String(length=36), nullable=True))
    op.add_column("attendance_logs", sa.Column("device_mapping_id", sa.Integer(), nullable=True))
    op.create_index("ix_attendance_logs_employee_uuid", "attendance_logs", ["employee_uuid"])
    op.create_index("ix_attendance_logs_device_mapping_id", "attendance_logs", ["device_mapping_id"])
    op.create_foreign_key(
        "fk_attendance_logs_employee_uuid_employees",
        "attendance_logs",
        "employees",
        ["employee_uuid"],
        ["employee_uuid"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_attendance_logs_device_mapping_id_device_user_mappings",
        "attendance_logs",
        "device_user_mappings",
        ["device_mapping_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        INSERT INTO device_user_mappings (employee_uuid, device_id, device_user_id, valid_from, active)
        SELECT
            e.employee_uuid,
            l.device_id,
            e.device_user_id,
            COALESCE(MIN(l.timestamp), e.created_at),
            true
        FROM employees e
        JOIN attendance_logs l
          ON l.employee_code = e.device_user_id
        GROUP BY e.employee_uuid, l.device_id, e.device_user_id, e.created_at
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO device_user_mappings (employee_uuid, device_id, device_user_id, valid_from, active)
        SELECT
            e.employee_uuid,
            'legacy-default',
            e.device_user_id,
            e.created_at,
            true
        FROM employees e
        WHERE NOT EXISTS (
            SELECT 1
            FROM device_user_mappings m
            WHERE m.employee_uuid = e.employee_uuid
        )
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE attendance_logs l
        SET employee_uuid = e.employee_uuid
        FROM employees e
        WHERE l.employee_uuid IS NULL
          AND l.employee_code = e.device_user_id
        """
    )
    op.execute(
        """
        UPDATE attendance_logs l
        SET device_mapping_id = m.id
        FROM device_user_mappings m
        WHERE l.device_mapping_id IS NULL
          AND m.device_id = l.device_id
          AND m.device_user_id = l.employee_code
          AND m.active = true
        """
    )

    op.drop_constraint("uq_log_employee_ts", "attendance_logs", type_="unique")
    op.create_unique_constraint(
        "uq_log_device_employee_ts",
        "attendance_logs",
        ["device_id", "employee_code", "timestamp"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_log_device_employee_ts", "attendance_logs", type_="unique")
    op.create_unique_constraint("uq_log_employee_ts", "attendance_logs", ["employee_code", "timestamp"])

    op.drop_constraint("fk_attendance_logs_device_mapping_id_device_user_mappings", "attendance_logs", type_="foreignkey")
    op.drop_constraint("fk_attendance_logs_employee_uuid_employees", "attendance_logs", type_="foreignkey")
    op.drop_index("ix_attendance_logs_device_mapping_id", table_name="attendance_logs")
    op.drop_index("ix_attendance_logs_employee_uuid", table_name="attendance_logs")
    op.drop_column("attendance_logs", "device_mapping_id")
    op.drop_column("attendance_logs", "employee_uuid")

    op.drop_index("uq_active_mapping_per_employee_device", table_name="device_user_mappings")
    op.drop_index("uq_active_mapping_per_device_identity", table_name="device_user_mappings")
    op.drop_index("ix_device_user_mappings_device_user_id", table_name="device_user_mappings")
    op.drop_index("ix_device_user_mappings_device_id", table_name="device_user_mappings")
    op.drop_index("ix_device_user_mappings_employee_uuid", table_name="device_user_mappings")
    op.drop_table("device_user_mappings")

    op.drop_index("ix_employees_employee_uuid", table_name="employees")
    op.drop_column("employees", "employee_uuid")
