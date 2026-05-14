"""Add firmware certification, runtime health, governance, and fleet metrics.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("mode", sa.String(length=16), server_default="NORMAL", nullable=False))
    op.add_column("devices", sa.Column("quarantine_reason", sa.String(length=1000), nullable=True))
    op.create_index("ix_devices_mode", "devices", ["mode"])

    op.create_table(
        "certified_firmware_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("firmware_version", sa.String(length=128), nullable=False),
        sa.Column("device_family", sa.String(length=128), nullable=True),
        sa.Column("vendor", sa.String(length=128), nullable=True),
        sa.Column("certification_status", sa.String(length=32), server_default="UNCERTIFIED", nullable=False),
        sa.Column("supported_operations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unsafe_operations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reconnect_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("known_bugs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("write_stability_score", sa.Integer(), server_default="50", nullable=False),
        sa.Column("verification_strategy", sa.String(length=64), server_default="strict_readback", nullable=False),
        sa.Column("rollout_recommendation", sa.String(length=128), nullable=True),
        sa.Column("operational_notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firmware_version"),
    )
    op.create_index("ix_certified_firmware_profiles_firmware_version", "certified_firmware_profiles", ["firmware_version"])
    op.create_index("ix_certified_firmware_profiles_certification_status", "certified_firmware_profiles", ["certification_status"])

    op.create_table(
        "device_runtime_health",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("connection_stability_score", sa.Integer(), server_default="100", nullable=False),
        sa.Column("timeout_frequency", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reconnect_frequency", sa.Integer(), server_default="0", nullable=False),
        sa.Column("protocol_error_rate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("verification_failure_rate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("drift_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("operational_risk_level", sa.String(length=16), server_default="LOW", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_device_runtime_health_device_id", "device_runtime_health", ["device_id"])
    op.create_index("ix_device_runtime_health_operational_risk_level", "device_runtime_health", ["operational_risk_level"])

    op.create_table(
        "operator_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("approval_uuid", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("requires_dual_confirmation", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("request_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approval_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_uuid"),
    )
    op.create_index("ix_operator_approvals_approval_uuid", "operator_approvals", ["approval_uuid"])
    op.create_index("ix_operator_approvals_action_type", "operator_approvals", ["action_type"])
    op.create_index("ix_operator_approvals_target_entity", "operator_approvals", ["target_entity"])
    op.create_index("ix_operator_approvals_status", "operator_approvals", ["status"])
    op.create_index("ix_operator_approvals_requested_by", "operator_approvals", ["requested_by"])
    op.create_index("ix_operator_approvals_approved_by", "operator_approvals", ["approved_by"])

    op.create_table(
        "fleet_health_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=32), server_default="GLOBAL", nullable=False),
        sa.Column("scope_id", sa.String(length=128), server_default="global", nullable=False),
        sa.Column("office_health", sa.Integer(), server_default="100", nullable=False),
        sa.Column("regional_health", sa.Integer(), server_default="100", nullable=False),
        sa.Column("failing_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("drift_hotspots", sa.Integer(), server_default="0", nullable=False),
        sa.Column("firmware_risk_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("queue_pressure", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reconciliation_backlog", sa.Integer(), server_default="0", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fleet_health_metrics_scope", "fleet_health_metrics", ["scope"])
    op.create_index("ix_fleet_health_metrics_scope_id", "fleet_health_metrics", ["scope_id"])
    op.create_index("ix_fleet_health_metrics_captured_at", "fleet_health_metrics", ["captured_at"])

    op.create_table(
        "system_control_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("singleton_key", sa.String(length=32), server_default="global", nullable=False),
        sa.Column("maintenance_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("emergency_freeze_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("changed_by", sa.String(length=36), nullable=True),
        sa.Column("change_reason", sa.String(length=1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key"),
    )

    op.execute(
        """
        INSERT INTO system_control_state (singleton_key, maintenance_mode, emergency_freeze_mode)
        VALUES ('global', false, false)
        ON CONFLICT (singleton_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("system_control_state")

    op.drop_index("ix_fleet_health_metrics_captured_at", table_name="fleet_health_metrics")
    op.drop_index("ix_fleet_health_metrics_scope_id", table_name="fleet_health_metrics")
    op.drop_index("ix_fleet_health_metrics_scope", table_name="fleet_health_metrics")
    op.drop_table("fleet_health_metrics")

    op.drop_index("ix_operator_approvals_approved_by", table_name="operator_approvals")
    op.drop_index("ix_operator_approvals_requested_by", table_name="operator_approvals")
    op.drop_index("ix_operator_approvals_status", table_name="operator_approvals")
    op.drop_index("ix_operator_approvals_target_entity", table_name="operator_approvals")
    op.drop_index("ix_operator_approvals_action_type", table_name="operator_approvals")
    op.drop_index("ix_operator_approvals_approval_uuid", table_name="operator_approvals")
    op.drop_table("operator_approvals")

    op.drop_index("ix_device_runtime_health_operational_risk_level", table_name="device_runtime_health")
    op.drop_index("ix_device_runtime_health_device_id", table_name="device_runtime_health")
    op.drop_table("device_runtime_health")

    op.drop_index("ix_certified_firmware_profiles_certification_status", table_name="certified_firmware_profiles")
    op.drop_index("ix_certified_firmware_profiles_firmware_version", table_name="certified_firmware_profiles")
    op.drop_table("certified_firmware_profiles")

    op.drop_index("ix_devices_mode", table_name="devices")
    op.drop_column("devices", "quarantine_reason")
    op.drop_column("devices", "mode")
