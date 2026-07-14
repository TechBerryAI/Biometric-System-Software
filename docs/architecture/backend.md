# Backend Architecture

## Runtime Stack

- FastAPI (`backend/app/main.py` — middleware + router includes only)
- SQLAlchemy + Alembic
- Celery worker/beat (`app/workers/`)
- Redis broker + distributed locks
- pyzk integration through defensive adapter (`app/domains/devices/services/pyzk_adapter.py`)
- Optional advisory AI (`app/ai/`)

## Package Layout

Domain-oriented application package:

```text
backend/app/
  main.py
  core/                 # config, database, security, device_policy, redis_keys
  shared/               # cross-domain helpers (device_exceptions, keep_list)
  domains/
    auth/               # router, schemas, models, services
    employees/
    attendance/
    devices/
    ops/                # ops router + /health* probes
  ai/                   # providers, prompts, insight/anomaly services
  workers/              # Celery app + tasks
```

ORM model aggregators for Alembic remain at `app/models/__init__.py` (re-exports domain models).

## API Domains

| Prefix | Role |
|--------|------|
| `/auth` | bootstrap, login, refresh, logout, me, password, user create |
| `/employees` | CRUD, soft offboard, daily attendance |
| `/attendance` | logs, sessions, daily summary |
| `/attendance/adjust` | correction capabilities / preview / apply |
| `/sync` | manual device sync |
| `/ops` | device command queue + operational metrics |
| `/insights` | management + anomaly insights (advisory) |
| `/health*` | liveness + dependency probes |

## Device Command Pipeline

Primary persistence:

- `device_commands` (durable queue in PostgreSQL)
- Device metadata writes only (`UPSERT_USER` / `DELETE_USER` / attendance corrections) — **no biometric templates**

Execution path:

1. Enqueue command with idempotency key
2. Claim pending commands (one active per device claim cycle)
3. Process under Redis per-device lock + verification readback
4. Recovery tasks handle stale commands

## Attendance Truth

- Append-only `attendance_logs`
- Derived/rebuildable `attendance_sessions`

## Tests

All backend tests remain under `backend/tests/` (`unit`, `api`, `integration`, `workers`, `e2e_scenarios`).

## Security Boundaries

- RBAC permission checks on operational routes
- Request correlation IDs via middleware
- Device mutations blocked by governance / device policy flags
