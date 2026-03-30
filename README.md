# Biometric attendance system

Connects this software to your existing biometric installation: **read-only** integration with ZKTeco / ESSL terminals (shadow mode), PostgreSQL storage, session processing, and a React dashboard.

## Layout

```
.
├── backend/          # FastAPI, SQLAlchemy, Alembic, Celery, pyzk
├── frontend/         # Vite + React + TypeScript + Tailwind
├── start.js          # Local dev: venv, migrations, API + Vite
└── README.md
```

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** (for the frontend)
- **PostgreSQL 14+** (local install, e.g. Windows + pgAdmin)
- **Redis** (optional — only if you run Celery for device polling)

## Database setup (PostgreSQL)

1. **Install PostgreSQL** and start the service (default port **5432**).

2. **Create an empty database** (e.g. in pgAdmin: right-click *Databases* → Create → name `biometric_db`).  
   Or run the sample script as superuser `postgres`:

   - File: `backend/scripts/setup_local_database.sql`

3. **Configure `backend/.env`** (copy from `backend/.env.example` if needed):

   ```env
   DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/biometric_db
   ```

   Replace `YOUR_PASSWORD` with the password for PostgreSQL user `postgres` (the one you use in pgAdmin).  
   If your database name or user differs, change the URL accordingly.

   **Special characters in the password** must be URL-encoded in `DATABASE_URL` (e.g. `@` → `%40`).

4. **Apply schema** (creates tables inside `biometric_db`):

   ```bash
   cd backend
   .venv\Scripts\activate
   pip install -r requirements.txt
   alembic upgrade head
   ```

## Quick start (full stack)

From the **repository root** (creates venv if needed, installs deps, runs migrations, starts API + Vite):

```bash
node start.js
```

- API: [http://localhost:8000/docs](http://localhost:8000/docs)
- UI: [http://localhost:5173](http://localhost:5173)

Set `VITE_API_URL=http://localhost:8000` if the frontend cannot reach the API (default in local dev).

### Celery + Redis (biometric device polling)

The HTTP API does not require Redis. Celery does:

```bash
set START_CELERY=1
node start.js
```

Install Redis locally and keep `REDIS_URL=redis://localhost:6379/0` in `backend/.env`, or point it at your Redis instance.

### Manual backend / frontend (without `start.js`)

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Celery** (optional, two terminals):

```bash
cd backend
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
```

**Scripts** (same logic as scheduled tasks):

```bash
cd backend
python scripts/sync_users.py
python scripts/poll_device.py
```

**Frontend**

```bash
cd frontend
npm install
set VITE_API_URL=http://localhost:8000
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

See `backend/.env.example` for all variables (database, Redis, ZK device, `TIMEZONE`, `DEVICE_POLL_INTERVAL_SECONDS`).
