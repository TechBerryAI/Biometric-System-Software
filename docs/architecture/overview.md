# Architecture Overview

## Platform Goal

This platform is built for **safe coexistence** with biometric edge devices that are inherently unreliable.  
The architecture prioritizes:

- deterministic attendance truth in PostgreSQL
- asynchronous, replay-safe device writes
- strict verification after mutation
- reconciliation and drift recovery
- operational governance and quarantine controls

## High-Level Components

- **Frontend (`frontend/`)**
  - React + Vite + TypeScript
  - Dashboard, attendance views, employee flows, operations center, and audit screens
- **Backend API (`backend/app/main.py`)**
  - FastAPI REST interface for business operations, health, and metrics
- **Device Orchestration**
  - `device_commands` queue in PostgreSQL
  - Celery workers and beat schedules for command processing, reconciliation, snapshots, retention
- **Persistence**
  - PostgreSQL for canonical attendance, identity lineage, command history, and governance records
  - Redis for Celery broker/backend and distributed locks
- **AI Layer**
  - advisory and analytics only
  - isolated from attendance truth mutation paths

## Core Reliability Model

1. API mutation request creates a durable queue command.
2. Worker claims command with per-device serialization.
3. Device write executes with pyzk containment adapter and lock heartbeat.
4. Immediate readback verification is mandatory.
5. Result is persisted to verification and execution history tables.
6. Reconciliation jobs are raised for mismatches/unsafe conditions.
7. Runtime risk scoring can auto-shift device mode to degraded/quarantined.

## Data Integrity Boundaries

- `attendance_logs` is append-only attendance truth.
- `attendance_sessions` is derived and rebuildable from logs.
- `employee_uuid` is immutable identity.
- `device_user_mappings` preserves identity lineage over time.
- Device operations are constrained to non-destructive metadata synchronization only.

## Governance and Safety Modes

- Global:
  - maintenance mode
  - emergency freeze mode
- Per device:
  - `NORMAL`
  - `READ_ONLY`
  - `DEGRADED`
  - `QUARANTINED`
  - `OFFLINE`

## Documentation Links

- Backend details: `architecture/backend.md`
- Frontend details: `architecture/frontend.md`
- Reliability and operations: `operations/reliability.md`
- Deployments: `operations/deployment.md`
