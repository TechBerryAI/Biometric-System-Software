# Deployment and Environments

## Environment Topology

Minimum production components:

- backend API service
- Celery worker
- Celery beat scheduler
- PostgreSQL
- Redis
- frontend web app

## Required Environment Files

- `backend/.env` (copy from `backend/.env.example`)
- frontend environment variable `VITE_API_URL` at build/runtime

## Critical Backend Variables

- Database/Redis:
  - `DATABASE_URL`
  - `REDIS_URL`
  - `REDIS_NAMESPACE`
- Device:
  - `ZK_DEVICE_IP`, `ZK_DEVICE_PORT`, `ZK_DEVICE_PASSWORD`, `ZK_DEVICE_TIMEOUT_SECONDS`, `ZK_DEVICE_ID`
- Queue/reconciliation:
  - `COMMAND_*`
  - `RECONCILIATION_INTERVAL_SECONDS`
  - `SNAPSHOT_INTERVAL_SECONDS`
- Governance:
  - `DEVICE_READ_ONLY`
  - `ALLOW_DEVICE_UID_REWRITE`
  - `ALLOW_DEVICE_PRIVILEGE_UPDATE`
  - `ALLOW_DEVICE_CARD_REWRITE`
  - `ALLOW_DEVICE_ADMIN_OVERRIDE`
- Retention:
  - `SNAPSHOT_RETENTION_DAYS`
  - `COMMAND_HISTORY_RETENTION_DAYS`
  - `RECONCILIATION_RETENTION_DAYS`
  - `METRICS_RETENTION_DAYS`

## Local Developer Start

From repo root:

```bash
node start.js
```

Optional Celery startup:

```bash
set START_CELERY=1
node start.js
```

## Production Rollout Order

1. Deploy DB migrations (`alembic upgrade head`)
2. Deploy backend API
3. Deploy Celery worker and beat
4. Deploy frontend with correct `VITE_API_URL`
5. Validate:
   - `/health`
   - `/health/db`
   - `/health/redis`
   - `/health/devices`
   - `/operations/alerts`

## Production Safety Checklist

- strong `JWT_SECRET_KEY`
- auth bootstrap credentials removed after first admin setup
- `DEVICE_READ_ONLY=true` during initial cutover
- firmware certification rows seeded and reviewed
- dashboards and alerts verified before enabling writes
