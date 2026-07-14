"""Simplify schema: attendance_logs SoT; drop correction/forensics/governance tables.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    # Preserve correction-sourced punches into attendance_logs before dropping overlays.
    if "attendance_effective_punches" in tables and "attendance_logs" in tables and "employees" in tables:
        op.execute(
            sa.text(
                """
                INSERT INTO attendance_logs (
                    employee_code, timestamp, device_id, employee_uuid, device_mapping_id, punch_type, created_at
                )
                SELECT
                    e.device_user_id,
                    ep.timestamp,
                    COALESCE(
                        (
                            SELECT al2.device_id
                            FROM attendance_logs al2
                            WHERE al2.employee_code = e.device_user_id
                            ORDER BY al2.timestamp DESC
                            LIMIT 1
                        ),
                        'device'
                    ),
                    e.employee_uuid,
                    NULL,
                    ep.punch_type,
                    COALESCE(ep.created_at, NOW())
                FROM attendance_effective_punches ep
                JOIN employees e ON e.id = ep.employee_id
                WHERE ep.is_active IS TRUE
                  AND ep.source = 'correction'
                ON CONFLICT DO NOTHING
                """
            )
        )

    drop_order = [
        "attendance_sync_suppressions",
        "attendance_correction_events",
        "attendance_corrections",
        "attendance_effective_punches",
        "attendance_events",
        "attendance_anomalies",
        "verification_results",
        "command_execution_history",
        "device_state_snapshots",
        "device_sync_events",
        "device_runtime_health",
        "device_firmware_profiles",
        "certified_firmware_profiles",
        "operation_safety_profiles",
        "reconciliation_jobs",
        "fleet_health_metrics",
        "operator_approvals",
        "audit_logs",
    ]
    for table in drop_order:
        if table in tables:
            op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError("Downgrade from schema simplification 0018 is not supported.")
