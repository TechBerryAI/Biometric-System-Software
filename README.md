# Biometric attendance system

Connects this software to your existing biometric installation: **read-only** integration with ZKTeco / ESSL terminals (shadow mode), PostgreSQL storage, session processing, and a React dashboard.

## Layout

```
.
├── backend/          # FastAPI, SQLAlchemy, Alembic, Celery, pyzk
├── frontend/         # Vite + React + TypeScript + Tailwind
├── docker-compose.yml
└── README.md
```

## Prerequisites

- Docker and Docker Compose **or** Python 3.11+, Node 20+, PostgreSQL 16+, Redis 7+

### Quick start (local dev)

From the **repository root** (installs venv, npm, runs migrations, starts API + Vite):

```bash
node start.js
```

This brings up **Postgres and Redis in Docker** (if Docker is installed) using **host ports 5433 and 6380** so they do not clash with a typical local PostgreSQL on **5432**. `start.js` sets `backend/.env` to those ports whenever you are **not** using `SKIP_DOCKER=1`, even if Docker fails to start—so the app does not accidentally hit your host Postgres on `5432`. **Docker Desktop must be running** on Windows; if you see a pipe error, open Docker Desktop and wait until it is ready, then run again.

Use `SKIP_DOCKER=1` if you manage Postgres/Redis yourself. Use `START_JS_NO_ENV_SYNC=1` to keep `backend/.env` unchanged (advanced).

## Run with Docker

From the **repository root**:

```bash
docker compose up --build
```

**Host ports** (from your machine): Postgres **5433** → container 5432; Redis **6380** → container 6379. Containers still talk to `postgres:5432` and `redis:6379` on the internal network.

Services:

| Service         | Port  | Role                                      |
|----------------|-------|-------------------------------------------|
| `backend`      | 8000  | REST API (`/health`, `/employees`, …)     |
| `frontend`     | 5173  | UI                                        |
| `postgres`     | 5433  | Database (host; maps to 5432 in container) |
| `redis`        | 6380  | Celery broker (host; maps to 6379 in container) |
| `celery_worker`| —     | Polls device & writes logs                |
| `celery_beat`  | —     | Schedules poll every 2 minutes (configurable) |

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- UI: [http://localhost:5173](http://localhost:5173)

The frontend calls the API at `http://localhost:8000` (set at build/runtime via `VITE_API_URL`).

### Reaching the device from Docker

The default device IP is `192.168.1.200`. Containers must reach that IP on your LAN.

- **Linux**: often works if the host can route to the device.
- **Windows / macOS Docker Desktop**: you may need `ZK_DEVICE_IP=host.docker.internal` and host routing, or run the backend worker on the host for polling.

Override in a `.env` next to `docker-compose.yml`:

```env
ZK_DEVICE_IP=192.168.1.200
TIMEZONE=Asia/Kolkata
```

## Local development (no Docker)

### Backend

```bash
cd backend
cp .env.example .env
# Defaults use localhost:5433 and localhost:6380 (see docker-compose host ports)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Celery (separate terminals):

```bash
cd backend
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
```

### One-shot scripts (same as worker logic)

```bash
cd backend
python scripts/sync_users.py
python scripts/poll_device.py
```

### Frontend

```bash
cd frontend
npm install
set VITE_API_URL=http://localhost:8000   # Windows cmd
# export VITE_API_URL=http://localhost:8000
npm run dev
```

## API summary

| Method | Path                         | Description                                      |
|--------|------------------------------|--------------------------------------------------|
| GET    | `/health`                    | Liveness                                         |
| GET    | `/employees`                 | List employees                                   |
| POST   | `/employees`                 | Upsert metadata by `device_user_id` (DB only)    |
| GET    | `/attendance/logs`           | Raw punches (`from`, `to`, `employee_code`)      |
| GET    | `/attendance/sessions`       | Paired sessions (`from`, `to`, `employee_id`)    |
| GET    | `/attendance/daily-summary`  | Per-employee day rollup (`summary_date`)         |
| GET    | `/attendance/{employee_id}`  | Sessions for one employee                        |

## Safety rules

- **Device**: only `get_users()` and `get_attendance()` via pyzk — no template storage, no clearing attendance, no user provisioning on the device.
- **Identity**: `device_user_id` is the terminal’s user id; the API never mints a separate device identity.

## Configuration

See `backend/.env.example` for all variables (database, Redis, ZK connection, `TIMEZONE`, `DEVICE_POLL_INTERVAL_SECONDS`).
