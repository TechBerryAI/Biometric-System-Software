# Biometric Workforce Intelligence Platform

Enterprise-grade workforce attendance and operations platform with:

- immutable workforce identity and device mapping lineage
- replay-safe queued device writes with mandatory verification readback
- reconciliation and drift recovery workflows
- firmware certification and runtime risk containment
- governance controls (maintenance, emergency freeze, quarantine)
- React operations center and RBAC-protected APIs

## Documentation

All detailed docs are now in `docs/`.

- Start here: `docs/README.md`
- Architecture: `docs/architecture-overview.md`
- Backend internals: `docs/backend-architecture.md`
- Frontend architecture: `docs/frontend-architecture.md`
- Reliability/operations: `docs/operations-and-reliability.md`
- Deployment: `docs/deployment-and-environments.md`
- Runbooks: `docs/runbooks.md`
- API map: `docs/api-overview.md`

## Repository Layout

```text
.
├── backend/       # FastAPI, SQLAlchemy, Alembic, Celery, pyzk integration
├── frontend/      # React + Vite + TypeScript + Tailwind
├── docs/          # Architecture, deployment, runbooks, API docs
├── start.js       # Local full-stack bootstrap
└── README.md
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Redis (required for Celery worker/beat queues)

## Quick Start (Recommended)

From repository root:

```bash
node start.js
```

This will:

- create backend virtual environment if missing
- install backend and frontend dependencies
- run Alembic migrations
- start FastAPI API server
- start frontend Vite server

Default URLs:

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Frontend: [http://localhost:5173](http://localhost:5173)

## Enable Celery Worker + Beat

On Windows PowerShell:

```powershell
$env:START_CELERY="1"
node start.js
```

On Linux/macOS shell:

```bash
START_CELERY=1 node start.js
```

## Manual Setup (Backend + Frontend)

### 1) Configure backend environment

```bash
cd backend
copy .env.example .env
```

Update at minimum:

- `DATABASE_URL`
- `REDIS_URL`
- `ZK_DEVICE_IP`
- `JWT_SECRET_KEY`

### 2) Install backend and run migrations

Windows:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Linux/macOS:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3) Start Celery (separate terminals)

```bash
cd backend
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
```

### 4) Start frontend

```bash
cd frontend
npm install
npm run dev
```

If needed, set frontend API URL:

Windows PowerShell:

```powershell
$env:VITE_API_URL="http://localhost:8000"
npm run dev
```

Linux/macOS:

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

## Production-Grade Startup Checklist

Before enabling writes in production:

- run `alembic upgrade head`
- configure strong `JWT_SECRET_KEY`
- configure `AUTH_BOOTSTRAP_ADMIN_EMAIL` and `AUTH_BOOTSTRAP_ADMIN_PASSWORD` for initial bootstrap only
- validate Redis connectivity and Celery workers
- verify health endpoints:
  - `/health`
  - `/health/db`
  - `/health/redis`
  - `/health/devices`
  - `/health/queue`
- review `/operations/alerts`
- keep `DEVICE_READ_ONLY=true` during initial cutover until validation is complete

## Key Operational Endpoints

- Health: `/health/*`
- Operational metrics: `/ops/metrics`
- Operations center: `/operations/*`
- Governance controls: `/governance/*`

Full endpoint grouping is documented in `docs/api-overview.md`.

## Safety and Platform Guarantees

- No destructive biometric device operations are allowed.
- Biometric template operations are not part of this platform.
- Device writes are asynchronous, serialized per device, and verification-backed.
- Attendance truth remains append-only (`attendance_logs`) and sessions are derived/rebuildable.
- Reconciliation and quarantine controls are first-class operational mechanisms.

## Troubleshooting

- Check `backend/.env` for `DATABASE_URL` and `REDIS_URL`.
- If migrations fail, ensure PostgreSQL is running and credentials are correct.
- If queue is stuck, inspect:
  - `/operations/queue`
  - `/operations/dead-letters`
  - `/operations/alerts`
- If device behavior is unstable, use governance controls:
  - `/governance/maintenance`
  - `/governance/emergency-freeze`
  - `/governance/quarantine`
