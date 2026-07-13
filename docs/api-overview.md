# API Overview

Backend direct base URL (service): `http://localhost:8000`

Frontend-facing base URL (recommended behind reverse proxy): `/api`

Swagger UI: `/docs`

## Core Domains

- **Health**
  - `/health`
  - `/health/db`
  - `/health/redis`
  - `/health/devices`
  - `/health/ai`
  - `/health/queue`
  - `/health/reconciliation`

- **Authentication and RBAC**
  - `/auth/*` for login, refresh, logout, user provisioning

- **Employees and Attendance**
  - `/employees/*`
  - `/attendance/*`
  - `/attendance/adjust/*` for correction workflows
  - `/sync/device`

- **Forensics and Audit**
  - `/forensics/*` for raw events, correction ledger, device snapshots
  - `/ops/audit-logs`

- **Operational Admin (`/ops/*`)**
  - `/ops/audit-logs`
  - `/ops/device-commands`
  - `/ops/device-commands/{command_uuid}/process`
  - `/ops/metrics`
  - `/ops/firmware-certifications`
  - `/ops/firmware-profiles`
  - `/ops/reconciliation-jobs`

- **AI Insights (advisory only)**
  - `/insights/management`
  - `/insights/anomalies`

## API Usage Notes

- Device writes are asynchronous and queue-backed.
- Command success is not assumed until verification readback succeeds.
- Internal governance policy (`system_governance_service`) can block mutation routes when maintenance, emergency freeze, or quarantine modes are active.
- Operator-grade flows should always include request IDs and audit context.

## Governance Controls (Database)

HTTP governance endpoints were removed. Toggle global or device modes directly in PostgreSQL when required:

```sql
-- Emergency freeze
UPDATE system_control_state
SET emergency_freeze_mode = true,
    change_reason = '<reason>',
    updated_at = now()
WHERE singleton_key = 'global';

-- Device quarantine
UPDATE devices
SET mode = 'QUARANTINED',
    quarantine_reason = '<reason>'
WHERE name = '<device-name>';
```

Use `/ops/metrics` and `/health/queue` to confirm queue pressure and device state after changes.
