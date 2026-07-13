# Backend Architecture

## Runtime Stack

- FastAPI (`backend/app/main.py`)
- SQLAlchemy + Alembic
- Celery worker/beat
- Redis broker + distributed locks
- pyzk integration through defensive adapter (`app/services/pyzk_adapter.py`)

## API Domains

- `auth` - JWT sessions, refresh, RBAC
- `employee` - workforce metadata + queued device metadata sync
- `attendance` - logs, sessions, summary
- `sync` - device pull and session rebuild
- `ops` - operational metrics, audit logs, device commands, firmware certification
- `forensics` - correction ledger, raw events, device snapshots
- `insights` - AI management summaries and anomaly explanations (advisory only)

## Device Command Pipeline

Primary models and services:

- `device_commands`
- `command_execution_history`
- `verification_results`
- `device_sync_events`
- `reconciliation_jobs`
- `operation_safety_profiles`

Execution path:

1. `enqueue_device_command()` persists command with idempotency key.
2. `claim_pending_commands()` selects and marks commands `RUNNING`, one active per device claim cycle.
3. `process_command()`:
   - validates governance and safety profile
   - acquires Redis per-device lock
   - starts lock heartbeat
   - records pre-write snapshot
   - executes write via `DeviceService`
   - records post-write snapshot
   - verifies by readback
   - updates execution history and terminal status
4. Recovery tasks handle stale commands and reconciliation backlog.

## Firmware Safety Layer

- `device_firmware_profiles` - firmware capability and strategy metadata
- `certified_firmware_profiles` - enterprise certification matrix and rollout controls
- Uncertified/unstable firmware automatically triggers restricted behavior and write blocking.

## Runtime Health and Risk

- `device_runtime_health` tracks:
  - stability score
  - timeout/reconnect/protocol/verification error trends
  - drift score
  - operational risk level
- Risk level drives automatic mode transitions (degraded/quarantined).

## Retention and Scale Hygiene

Scheduled jobs include:

- periodic snapshots
- stale command recovery
- reconciliation processors
- fleet health aggregation
- retention pruning for snapshots/history/reconciliation/metrics

## Security Boundaries

- RBAC permission checks on operational routes
- audit logging for privileged actions
- request correlation IDs propagated via middleware
- device mutations blocked in emergency freeze/maintenance/device restricted modes
