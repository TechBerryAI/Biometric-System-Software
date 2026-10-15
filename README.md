# Biometric Workforce Intelligence Platform

Enterprise-grade workforce attendance and operations platform with:

- attendance + device operations around ZKTeco/ESSL terminals
- replay-safe queued device writes with mandatory verification readback
- append-only attendance truth with rebuildable sessions
- governance controls (maintenance, emergency freeze, quarantine)
- React operations center and RBAC-protected APIs

## Documentation

All detailed docs are in `docs/`.

- Start here: [`docs/README.md`](docs/README.md)
- Structure snapshot: [`docs/architecture/PROJECT_STRUCTURE.md`](docs/architecture/PROJECT_STRUCTURE.md)
- Architecture: [`docs/architecture/overview.md`](docs/architecture/overview.md)
- Backend: [`docs/architecture/backend.md`](docs/architecture/backend.md)
- Frontend: [`docs/architecture/frontend.md`](docs/architecture/frontend.md)
- Reliability: [`docs/operations/reliability.md`](docs/operations/reliability.md)
- Deployment: [`docs/operations/deployment.md`](docs/operations/deployment.md)
- Runbooks: [`docs/operations/runbooks.md`](docs/operations/runbooks.md)
- API map: [`docs/api/overview.md`](docs/api/overview.md)

## Repository Layout

```text
.
├── backend/       # FastAPI, SQLAlchemy, Alembic, Celery, pyzk integration
├── frontend/      # React + Vite + TypeScript + Tailwind (npm workspace)
├── e2e/           # Playwright end-to-end scenarios
├── docs/          # Architecture, API, operations, testing
├── scripts/       # Repo automation (start-vm, traceability check)
├── Makefile       # install / start / start-vm / test / clean
├── package.json   # npm workspaces root + Playwright
└── README.md
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+
- Redis (required for Celery worker/beat queues)

## Quick Start (Recommended)

### Local development

```bash
make install   # once
make start     # API :8000 + Celery + Vite :5173 (Ctrl+C stops all)
```

Run the test suite with:

```bash
make test
```

### VM app server

```bash
make start-vm
```

or:

```bash
npm run start:vm
```

`start-vm.js` (production mode; it does not install dependencies) will:

- wait for PostgreSQL and Redis, explaining any connection failure (`backend/scripts/check_services.py`)
- run Alembic migrations
- build the frontend when its sources changed, and serve it with compression and caching
- start the FastAPI API (multiple uvicorn workers), Celery worker + beat, and the web server
- restart any service that crashes, and clean up processes left by an earlier run

To keep it running after you log out and start it on boot, install it as a service:
see [deployment](docs/operations/deployment.md#run-as-a-service-systemd).

Default URLs:

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Frontend: [http://localhost:5173](http://localhost:5173)

## Enable Celery Worker + Beat

Both `make start` (local) and `npm run start:vm` (VM) start Celery worker + beat unless `START_CELERY=0` or `DEVICE_AUTO_SYNC_ENABLED=false`. To run them by hand, use separate terminals (see Manual Setup below).

## Manual Setup (Backend + Frontend)

### 1) Configure backend environment

```bash
cd backend
cp .env.example .env
```

Update at minimum:

- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`

Device IP/port/timezone are managed in the Settings UI after first run. Optional `ZK_DEVICE_IP` / `ZK_DEVICE_PORT` / `TIMEZONE` only seed the first device row.

### 2) Install and run tests

```bash
make install
make test
```

### 3) Start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4) Start Celery (separate terminals)

```bash
cd backend
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
```

### 5) Start frontend

From repository root (npm workspaces):

```bash
npm install
npm run dev
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
  - `/ops/metrics`
- set `DEVICE_WRITES_ENABLED = False` in `backend/app/core/device_policy.py` during initial cutover until validation is complete

## Key Operational Endpoints

- Health: `/health/*`
- Operational metrics: `/ops/metrics`
- Device command queue: `/ops/device-commands`
- Insights: `/insights/*`

Full endpoint grouping is documented in [`docs/api/overview.md`](docs/api/overview.md).

## Safety and Platform Guarantees

- No destructive biometric device operations are allowed.
- Biometric template operations are not part of this platform.
- Device writes are asynchronous, serialized per device, and verification-backed.
- Attendance truth remains append-only (`attendance_logs`) and sessions are derived/rebuildable.

## Troubleshooting

- Check `backend/.env` for `DATABASE_URL` and `REDIS_URL`.
- If login shows browser CORS/preflight errors on VM/LAN hosts, set `VITE_API_URL` correctly and verify backend CORS vars (`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_PRIVATE_NETWORK_ORIGINS`).
- If migrations fail, ensure PostgreSQL is running and credentials are correct.
- If queue is stuck, inspect `/ops/metrics` and `/ops/device-commands?status=DEAD_LETTER`.
- If device behavior is unstable, quarantine or freeze via PostgreSQL (see [`docs/api/overview.md`](docs/api/overview.md) and [`docs/operations/runbooks.md`](docs/operations/runbooks.md)).
