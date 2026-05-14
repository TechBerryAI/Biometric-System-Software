-- PostgreSQL schema for Biometric Attendance API
-- Matches Alembic revision 0003 (see alembic/versions/20260330_0001_initial_schema.py).
--
-- Apply to an empty database, for example:
--   psql -U postgres -d your_database -f schema.sql
--
-- If you use Alembic on the same database afterward, stamp the revision so upgrades
-- do not re-run:  alembic stamp 0003

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE employees (
    id SERIAL NOT NULL,
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
    PRIMARY KEY (id),
    CONSTRAINT uq_employees_device_user_id UNIQUE (device_user_id)
);

CREATE TABLE attendance_logs (
    id SERIAL NOT NULL,
    employee_code VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    punch_type VARCHAR(32) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_log_employee_ts UNIQUE (employee_code, timestamp)
);

CREATE INDEX ix_attendance_logs_employee_code ON attendance_logs (employee_code);

CREATE INDEX ix_attendance_logs_timestamp ON attendance_logs (timestamp);

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

INSERT INTO alembic_version (version_num) VALUES ('0003');

COMMIT;
