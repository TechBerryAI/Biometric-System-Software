# API Overview

Base URL (local): `http://localhost:8000`

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
  - `/sync/device`

- **Operational Admin**
  - `/ops/audit-logs`
  - `/ops/device-commands`
  - `/ops/metrics`
  - `/ops/firmware-certifications`

- **Enterprise Operations Center**
  - `/operations/queue`
  - `/operations/reconciliation`
  - `/operations/device-drift`
  - `/operations/firmware-health`
  - `/operations/firmware-certification`
  - `/operations/fleet-health`
  - `/operations/dead-letters`
  - `/operations/incident-timeline`
  - `/operations/alerts`

- **Governance**
  - `/governance/state`
  - `/governance/maintenance`
  - `/governance/emergency-freeze`
  - `/governance/quarantine`
  - `/governance/approvals/request`
  - `/governance/approvals/{approval_uuid}`

## API Usage Notes

- Device writes are asynchronous and queue-backed.
- Command success is not assumed until verification readback succeeds.
- Governance modes can block mutation routes.
- Operator-grade flows should always include request IDs and audit context.
