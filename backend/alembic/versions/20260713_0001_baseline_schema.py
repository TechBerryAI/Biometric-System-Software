"""Baseline schema: full platform DDL at revision 0015.

Revision ID: 0015
Revises:
Create Date: 2026-07-13

Squashed from migrations 0003-0015. Existing databases already stamped at 0015
require no upgrade; fresh databases apply this revision once.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BASELINE_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE employees (
    id SERIAL NOT NULL,
    employee_uuid VARCHAR(36) NOT NULL,
    device_user_id VARCHAR(64) NOT NULL,
    device_uid INTEGER,
    device_privilege INTEGER,
    device_group_id VARCHAR(64),
    device_card VARCHAR(128),
    name VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    shift_start TIME WITHOUT TIME ZONE,
    shift_end TIME WITHOUT TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    departed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_employees_device_user_id UNIQUE (device_user_id)
);

CREATE UNIQUE INDEX ix_employees_employee_uuid ON employees (employee_uuid);

CREATE TABLE device_user_mappings (
    id SERIAL NOT NULL,
    employee_uuid VARCHAR(36) NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    device_user_id VARCHAR(64) NOT NULL,
    valid_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    valid_to TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_device_user_mappings_employee_uuid_employees FOREIGN KEY (employee_uuid) REFERENCES employees (employee_uuid) ON DELETE CASCADE
);

CREATE INDEX ix_device_user_mappings_employee_uuid ON device_user_mappings (employee_uuid);
CREATE INDEX ix_device_user_mappings_device_id ON device_user_mappings (device_id);
CREATE INDEX ix_device_user_mappings_device_user_id ON device_user_mappings (device_user_id);
CREATE UNIQUE INDEX uq_active_mapping_per_device_identity ON device_user_mappings (device_id, device_user_id) WHERE active = true;
CREATE UNIQUE INDEX uq_active_mapping_per_employee_device ON device_user_mappings (employee_uuid, device_id) WHERE active = true;

CREATE TABLE attendance_logs (
    id SERIAL NOT NULL,
    employee_code VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    employee_uuid VARCHAR(36),
    device_mapping_id INTEGER,
    punch_type VARCHAR(32) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_log_device_employee_ts UNIQUE (device_id, employee_code, timestamp),
    CONSTRAINT fk_attendance_logs_employee_uuid_employees FOREIGN KEY (employee_uuid) REFERENCES employees (employee_uuid) ON DELETE SET NULL,
    CONSTRAINT fk_attendance_logs_device_mapping_id_device_user_mappings FOREIGN KEY (device_mapping_id) REFERENCES device_user_mappings (id) ON DELETE SET NULL
);

CREATE INDEX ix_attendance_logs_employee_code ON attendance_logs (employee_code);
CREATE INDEX ix_attendance_logs_timestamp ON attendance_logs (timestamp);
CREATE INDEX ix_attendance_logs_employee_uuid ON attendance_logs (employee_uuid);
CREATE INDEX ix_attendance_logs_device_mapping_id ON attendance_logs (device_mapping_id);

CREATE TABLE attendance_sessions (
    id SERIAL NOT NULL,
    employee_id INTEGER NOT NULL,
    check_in TIMESTAMP WITH TIME ZONE NOT NULL,
    check_out TIMESTAMP WITH TIME ZONE,
    work_duration INTEGER,
    late_minutes INTEGER,
    early_minutes INTEGER,
    status VARCHAR(32) DEFAULT 'complete' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_attendance_sessions_employee_id_employees FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
);

CREATE INDEX ix_attendance_sessions_employee_id ON attendance_sessions (employee_id);
CREATE INDEX ix_attendance_sessions_check_in ON attendance_sessions (check_in);

CREATE TABLE attendance_anomalies (
    id SERIAL NOT NULL,
    anomaly_key VARCHAR(128) NOT NULL,
    anomaly_date DATE NOT NULL,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    department VARCHAR(255),
    metric_value DOUBLE PRECISION,
    baseline_value DOUBLE PRECISION,
    description VARCHAR(600) NOT NULL,
    explanation VARCHAR(1000),
    recommendation VARCHAR(1000),
    metadata_json JSON NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_attendance_anomaly_key_date UNIQUE (anomaly_key, anomaly_date)
);

CREATE INDEX ix_attendance_anomalies_anomaly_key ON attendance_anomalies (anomaly_key);
CREATE INDEX ix_attendance_anomalies_anomaly_date ON attendance_anomalies (anomaly_date);
CREATE INDEX ix_attendance_anomalies_category ON attendance_anomalies (category);
CREATE INDEX ix_attendance_anomalies_department ON attendance_anomalies (department);

CREATE TABLE users (
    id SERIAL NOT NULL,
    user_uuid VARCHAR(36) NOT NULL,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(160),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    active BOOLEAN DEFAULT true NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (user_uuid),
    UNIQUE (email)
);

CREATE INDEX ix_users_user_uuid ON users (user_uuid);
CREATE INDEX ix_users_email ON users (email);

CREATE TABLE refresh_tokens (
    id SERIAL NOT NULL,
    token_id VARCHAR(36) NOT NULL,
    user_id INTEGER NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT false NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (token_id),
    UNIQUE (token_hash),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX ix_refresh_tokens_token_id ON refresh_tokens (token_id);
CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens (expires_at);

CREATE TABLE audit_logs (
    id SERIAL NOT NULL,
    actor_user_uuid VARCHAR(36),
    action_type VARCHAR(128) NOT NULL,
    entity_type VARCHAR(128) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    ip_address VARCHAR(64),
    request_id VARCHAR(64),
    metadata_json JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_actor_user_uuid ON audit_logs (actor_user_uuid);
CREATE INDEX ix_audit_logs_action_type ON audit_logs (action_type);
CREATE INDEX ix_audit_logs_entity_type ON audit_logs (entity_type);
CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id);
CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id);
CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp);

CREATE TABLE devices (
    id SERIAL NOT NULL,
    device_uuid VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    ip_address VARCHAR(128) NOT NULL,
    port INTEGER NOT NULL,
    location VARCHAR(255),
    timezone VARCHAR(64) NOT NULL,
    firmware_version VARCHAR(128),
    serial_number VARCHAR(128),
    capabilities JSONB,
    active BOOLEAN DEFAULT true NOT NULL,
    last_seen TIMESTAMP WITH TIME ZONE,
    health_status VARCHAR(32) DEFAULT 'UNKNOWN' NOT NULL,
    mode VARCHAR(16) DEFAULT 'NORMAL' NOT NULL,
    quarantine_reason VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (device_uuid)
);

CREATE INDEX ix_devices_device_uuid ON devices (device_uuid);
CREATE INDEX ix_devices_mode ON devices (mode);

CREATE TABLE device_commands (
    id SERIAL NOT NULL,
    command_uuid VARCHAR(36) NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    command_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) DEFAULT 'PENDING' NOT NULL,
    retries INTEGER DEFAULT 0 NOT NULL,
    retry_backoff_seconds INTEGER DEFAULT 0 NOT NULL,
    last_error VARCHAR(2000),
    correlation_id VARCHAR(128),
    initiated_by VARCHAR(36),
    initiated_from VARCHAR(64),
    verification_status VARCHAR(32),
    verification_details JSONB,
    firmware_profile VARCHAR(128),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    UNIQUE (command_uuid),
    UNIQUE (idempotency_key)
);

CREATE INDEX ix_device_commands_command_uuid ON device_commands (command_uuid);
CREATE INDEX ix_device_commands_device_id ON device_commands (device_id);
CREATE INDEX ix_device_commands_command_type ON device_commands (command_type);
CREATE INDEX ix_device_commands_status ON device_commands (status);
CREATE INDEX ix_device_commands_correlation_id ON device_commands (correlation_id);
CREATE INDEX ix_device_commands_idempotency_key ON device_commands (idempotency_key);
CREATE INDEX ix_device_commands_created_at ON device_commands (created_at);
CREATE INDEX ix_device_commands_next_attempt_at ON device_commands (next_attempt_at);
CREATE INDEX ix_device_commands_initiated_by ON device_commands (initiated_by);
CREATE INDEX ix_device_commands_verification_status ON device_commands (verification_status);
CREATE INDEX ix_device_commands_heartbeat_at ON device_commands (heartbeat_at);

CREATE TABLE device_sync_events (
    id SERIAL NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    event_source VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    details JSONB,
    correlation_id VARCHAR(128),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_device_sync_events_device_id ON device_sync_events (device_id);
CREATE INDEX ix_device_sync_events_event_type ON device_sync_events (event_type);
CREATE INDEX ix_device_sync_events_status ON device_sync_events (status);
CREATE INDEX ix_device_sync_events_correlation_id ON device_sync_events (correlation_id);
CREATE INDEX ix_device_sync_events_timestamp ON device_sync_events (timestamp);
CREATE INDEX ix_device_sync_events_event_source ON device_sync_events (event_source);

CREATE TABLE verification_results (
    id SERIAL NOT NULL,
    command_id INTEGER NOT NULL,
    verification_status VARCHAR(32) NOT NULL,
    expected_state JSONB NOT NULL,
    actual_state JSONB,
    mismatch_details JSONB,
    verified_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (command_id) REFERENCES device_commands (id) ON DELETE CASCADE
);

CREATE INDEX ix_verification_results_command_id ON verification_results (command_id);
CREATE INDEX ix_verification_results_verification_status ON verification_results (verification_status);
CREATE INDEX ix_verification_results_verified_at ON verification_results (verified_at);

CREATE TABLE device_firmware_profiles (
    id SERIAL NOT NULL,
    firmware_version VARCHAR(128) NOT NULL,
    supports_user_write BOOLEAN DEFAULT true NOT NULL,
    supports_name_update BOOLEAN DEFAULT true NOT NULL,
    supports_uid_update BOOLEAN DEFAULT true NOT NULL,
    supports_card_update BOOLEAN DEFAULT true NOT NULL,
    safe_write_strategy VARCHAR(64) NOT NULL,
    reconnect_required BOOLEAN DEFAULT true NOT NULL,
    write_delay_ms INTEGER DEFAULT 500 NOT NULL,
    verification_strategy VARCHAR(64) NOT NULL,
    known_limitations VARCHAR(2000),
    supports_attlog_delete_by_time BOOLEAN DEFAULT false NOT NULL,
    supports_attlog_write BOOLEAN DEFAULT false NOT NULL,
    attlog_record_size INTEGER DEFAULT 40 NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (firmware_version)
);

CREATE INDEX ix_device_firmware_profiles_firmware_version ON device_firmware_profiles (firmware_version);

CREATE TABLE reconciliation_jobs (
    id SERIAL NOT NULL,
    job_type VARCHAR(64) NOT NULL,
    target_entity VARCHAR(128) NOT NULL,
    status VARCHAR(32) DEFAULT 'PENDING' NOT NULL,
    findings JSONB,
    resolution JSONB,
    correlation_id VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
);

CREATE INDEX ix_reconciliation_jobs_job_type ON reconciliation_jobs (job_type);
CREATE INDEX ix_reconciliation_jobs_target_entity ON reconciliation_jobs (target_entity);
CREATE INDEX ix_reconciliation_jobs_status ON reconciliation_jobs (status);
CREATE INDEX ix_reconciliation_jobs_correlation_id ON reconciliation_jobs (correlation_id);
CREATE INDEX ix_reconciliation_jobs_created_at ON reconciliation_jobs (created_at);

CREATE TABLE command_execution_history (
    id SERIAL NOT NULL,
    command_id INTEGER NOT NULL,
    execution_attempt INTEGER NOT NULL,
    execution_hash VARCHAR(128) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    worker_id VARCHAR(128),
    verification_result VARCHAR(32),
    final_status VARCHAR(32) DEFAULT 'RUNNING' NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_execution_history_command_attempt UNIQUE (command_id, execution_attempt),
    FOREIGN KEY (command_id) REFERENCES device_commands (id) ON DELETE CASCADE
);

CREATE INDEX ix_command_execution_history_command_id ON command_execution_history (command_id);
CREATE INDEX ix_command_execution_history_execution_hash ON command_execution_history (execution_hash);
CREATE INDEX ix_command_execution_history_started_at ON command_execution_history (started_at);
CREATE INDEX ix_command_execution_history_worker_id ON command_execution_history (worker_id);
CREATE INDEX ix_command_execution_history_verification_result ON command_execution_history (verification_result);
CREATE INDEX ix_command_execution_history_final_status ON command_execution_history (final_status);

CREATE TABLE device_state_snapshots (
    id SERIAL NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    snapshot_type VARCHAR(32) NOT NULL,
    snapshot_hash VARCHAR(128) NOT NULL,
    user_count INTEGER NOT NULL,
    user_metadata JSONB NOT NULL,
    firmware_version VARCHAR(128),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_device_state_snapshots_device_id ON device_state_snapshots (device_id);
CREATE INDEX ix_device_state_snapshots_snapshot_type ON device_state_snapshots (snapshot_type);
CREATE INDEX ix_device_state_snapshots_snapshot_hash ON device_state_snapshots (snapshot_hash);
CREATE INDEX ix_device_state_snapshots_firmware_version ON device_state_snapshots (firmware_version);
CREATE INDEX ix_device_state_snapshots_captured_at ON device_state_snapshots (captured_at);

CREATE TABLE operation_safety_profiles (
    id SERIAL NOT NULL,
    operation_type VARCHAR(64) NOT NULL,
    firmware_compatibility JSONB,
    risk_level VARCHAR(16) DEFAULT 'SAFE' NOT NULL,
    verification_required BOOLEAN DEFAULT true NOT NULL,
    rollback_possible BOOLEAN DEFAULT false NOT NULL,
    retry_safe BOOLEAN DEFAULT true NOT NULL,
    requires_manual_review BOOLEAN DEFAULT false NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (operation_type)
);

CREATE INDEX ix_operation_safety_profiles_operation_type ON operation_safety_profiles (operation_type);

CREATE TABLE certified_firmware_profiles (
    id SERIAL NOT NULL,
    firmware_version VARCHAR(128) NOT NULL,
    device_family VARCHAR(128),
    vendor VARCHAR(128),
    certification_status VARCHAR(32) DEFAULT 'UNCERTIFIED' NOT NULL,
    supported_operations JSONB,
    unsafe_operations JSONB,
    reconnect_requirements JSONB,
    known_bugs JSONB,
    write_stability_score INTEGER DEFAULT 50 NOT NULL,
    verification_strategy VARCHAR(64) DEFAULT 'strict_readback' NOT NULL,
    rollout_recommendation VARCHAR(128),
    operational_notes VARCHAR(2000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (firmware_version)
);

CREATE INDEX ix_certified_firmware_profiles_firmware_version ON certified_firmware_profiles (firmware_version);
CREATE INDEX ix_certified_firmware_profiles_certification_status ON certified_firmware_profiles (certification_status);

CREATE TABLE device_runtime_health (
    id SERIAL NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    connection_stability_score INTEGER DEFAULT 100 NOT NULL,
    timeout_frequency INTEGER DEFAULT 0 NOT NULL,
    reconnect_frequency INTEGER DEFAULT 0 NOT NULL,
    protocol_error_rate INTEGER DEFAULT 0 NOT NULL,
    verification_failure_rate INTEGER DEFAULT 0 NOT NULL,
    drift_score INTEGER DEFAULT 0 NOT NULL,
    operational_risk_level VARCHAR(16) DEFAULT 'LOW' NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (device_id)
);

CREATE INDEX ix_device_runtime_health_device_id ON device_runtime_health (device_id);
CREATE INDEX ix_device_runtime_health_operational_risk_level ON device_runtime_health (operational_risk_level);

CREATE TABLE operator_approvals (
    id SERIAL NOT NULL,
    approval_uuid VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    target_entity VARCHAR(128) NOT NULL,
    requested_by VARCHAR(36),
    approved_by VARCHAR(36),
    status VARCHAR(32) DEFAULT 'PENDING' NOT NULL,
    requires_dual_confirmation BOOLEAN DEFAULT true NOT NULL,
    request_details JSONB,
    approval_details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    UNIQUE (approval_uuid)
);

CREATE INDEX ix_operator_approvals_approval_uuid ON operator_approvals (approval_uuid);
CREATE INDEX ix_operator_approvals_action_type ON operator_approvals (action_type);
CREATE INDEX ix_operator_approvals_target_entity ON operator_approvals (target_entity);
CREATE INDEX ix_operator_approvals_status ON operator_approvals (status);
CREATE INDEX ix_operator_approvals_requested_by ON operator_approvals (requested_by);
CREATE INDEX ix_operator_approvals_approved_by ON operator_approvals (approved_by);

CREATE TABLE fleet_health_metrics (
    id SERIAL NOT NULL,
    scope VARCHAR(32) DEFAULT 'GLOBAL' NOT NULL,
    scope_id VARCHAR(128) DEFAULT 'global' NOT NULL,
    office_health INTEGER DEFAULT 100 NOT NULL,
    regional_health INTEGER DEFAULT 100 NOT NULL,
    failing_devices INTEGER DEFAULT 0 NOT NULL,
    drift_hotspots INTEGER DEFAULT 0 NOT NULL,
    firmware_risk_distribution JSONB,
    queue_pressure INTEGER DEFAULT 0 NOT NULL,
    reconciliation_backlog INTEGER DEFAULT 0 NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_fleet_health_metrics_scope ON fleet_health_metrics (scope);
CREATE INDEX ix_fleet_health_metrics_scope_id ON fleet_health_metrics (scope_id);
CREATE INDEX ix_fleet_health_metrics_captured_at ON fleet_health_metrics (captured_at);

CREATE TABLE system_control_state (
    id SERIAL NOT NULL,
    singleton_key VARCHAR(32) DEFAULT 'global' NOT NULL,
    maintenance_mode BOOLEAN DEFAULT false NOT NULL,
    emergency_freeze_mode BOOLEAN DEFAULT false NOT NULL,
    changed_by VARCHAR(36),
    change_reason VARCHAR(1000),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (singleton_key)
);


CREATE INDEX ix_employees_departed_at ON employees (departed_at);

CREATE TABLE attendance_corrections (
    id SERIAL NOT NULL,
    correction_uuid VARCHAR(36) NOT NULL,
    employee_id INTEGER NOT NULL,
    local_date DATE NOT NULL,
    previous_check_in TIMESTAMP WITH TIME ZONE,
    previous_check_out TIMESTAMP WITH TIME ZONE,
    new_check_in TIMESTAMP WITH TIME ZONE,
    new_check_out TIMESTAMP WITH TIME ZONE,
    actor_user_uuid VARCHAR(36),
    device_command_uuid VARCHAR(36),
    status VARCHAR(32) DEFAULT 'pending' NOT NULL,
    error_message VARCHAR(2000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE,
    device_tier VARCHAR(1),
    device_verification_details JSONB,
    correction_mode VARCHAR(32),
    device_operation_uuid VARCHAR(36),
    reimport_completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    UNIQUE (correction_uuid),
    UNIQUE (device_operation_uuid),
    FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
);

CREATE INDEX ix_attendance_corrections_employee_id ON attendance_corrections (employee_id);
CREATE INDEX ix_attendance_corrections_local_date ON attendance_corrections (local_date);
CREATE INDEX ix_attendance_corrections_actor_user_uuid ON attendance_corrections (actor_user_uuid);
CREATE INDEX ix_attendance_corrections_device_command_uuid ON attendance_corrections (device_command_uuid);
CREATE INDEX ix_attendance_corrections_device_operation_uuid ON attendance_corrections (device_operation_uuid);
CREATE INDEX ix_attendance_corrections_employee_date_status ON attendance_corrections (employee_id, local_date, status);

CREATE TABLE attendance_sync_suppressions (
    id SERIAL NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    employee_code VARCHAR(64) NOT NULL,
    suppressed_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    reason VARCHAR(32) DEFAULT 'correction' NOT NULL,
    correction_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_suppression_device_employee_ts UNIQUE (device_id, employee_code, suppressed_timestamp),
    FOREIGN KEY (correction_id) REFERENCES attendance_corrections (id) ON DELETE SET NULL
);

CREATE INDEX ix_attendance_sync_suppressions_device_id ON attendance_sync_suppressions (device_id);
CREATE INDEX ix_attendance_sync_suppressions_employee_code ON attendance_sync_suppressions (employee_code);
CREATE INDEX ix_attendance_sync_suppressions_suppressed_timestamp ON attendance_sync_suppressions (suppressed_timestamp);

CREATE TABLE attendance_events (
    id SERIAL NOT NULL,
    event_uuid VARCHAR(36) NOT NULL,
    employee_code VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    employee_uuid VARCHAR(36),
    device_mapping_id INTEGER,
    punch_type VARCHAR(32) NOT NULL,
    source VARCHAR(32) DEFAULT 'device_sync' NOT NULL,
    sync_batch_uuid VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_event_device_employee_ts UNIQUE (device_id, employee_code, timestamp),
    CONSTRAINT uq_attendance_event_uuid UNIQUE (event_uuid),
    FOREIGN KEY (device_mapping_id) REFERENCES device_user_mappings (id) ON DELETE SET NULL,
    FOREIGN KEY (employee_uuid) REFERENCES employees (employee_uuid) ON DELETE SET NULL
);

CREATE INDEX ix_attendance_events_employee_code ON attendance_events (employee_code);
CREATE INDEX ix_attendance_events_timestamp ON attendance_events (timestamp);
CREATE INDEX ix_attendance_events_employee_uuid ON attendance_events (employee_uuid);
CREATE INDEX ix_attendance_events_sync_batch_uuid ON attendance_events (sync_batch_uuid);

CREATE TABLE attendance_effective_punches (
    id SERIAL NOT NULL,
    employee_id INTEGER NOT NULL,
    local_date DATE NOT NULL,
    punch_type VARCHAR(32) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    source VARCHAR(32) DEFAULT 'derived' NOT NULL,
    correction_uuid VARCHAR(36),
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE
);

CREATE INDEX ix_effective_punches_employee_date ON attendance_effective_punches (employee_id, local_date);
CREATE INDEX ix_effective_punches_timestamp ON attendance_effective_punches (timestamp);
CREATE INDEX ix_effective_punches_active ON attendance_effective_punches (is_active);
CREATE INDEX ix_effective_punches_correction_uuid ON attendance_effective_punches (correction_uuid);

CREATE TABLE attendance_correction_events (
    id SERIAL NOT NULL,
    event_uuid VARCHAR(36) NOT NULL,
    correction_uuid VARCHAR(36) NOT NULL,
    device_operation_uuid VARCHAR(36),
    event_type VARCHAR(64) NOT NULL,
    payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_correction_event_uuid UNIQUE (event_uuid),
    CONSTRAINT uq_correction_device_operation_uuid UNIQUE (device_operation_uuid)
);

CREATE INDEX ix_correction_events_correction_uuid ON attendance_correction_events (correction_uuid);
CREATE INDEX ix_correction_events_event_type ON attendance_correction_events (event_type);

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
ON CONFLICT (operation_type) DO NOTHING;

INSERT INTO operation_safety_profiles (
    operation_type,
    firmware_compatibility,
    risk_level,
    verification_required,
    rollback_possible,
    retry_safe,
    requires_manual_review
) VALUES (
    'UPSERT_USER',
    '{"supported": ["*"]}'::jsonb,
    'MODERATE',
    true,
    false,
    true,
    false
)
ON CONFLICT (operation_type) DO NOTHING;

INSERT INTO system_control_state (singleton_key, maintenance_mode, emergency_freeze_mode)
VALUES ('global', false, false)
ON CONFLICT (singleton_key) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(_BASELINE_SQL)


def downgrade() -> None:
    tables = [
        "attendance_correction_events",
        "attendance_effective_punches",
        "attendance_events",
        "attendance_sync_suppressions",
        "attendance_corrections",
        "fleet_health_metrics",
        "system_control_state",
        "operator_approvals",
        "device_runtime_health",
        "certified_firmware_profiles",
        "operation_safety_profiles",
        "device_state_snapshots",
        "command_execution_history",
        "reconciliation_jobs",
        "device_firmware_profiles",
        "verification_results",
        "device_sync_events",
        "device_commands",
        "devices",
        "audit_logs",
        "refresh_tokens",
        "users",
        "attendance_anomalies",
        "attendance_sessions",
        "attendance_logs",
        "device_user_mappings",
        "employees",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
