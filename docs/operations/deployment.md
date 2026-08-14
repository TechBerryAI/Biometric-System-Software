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
- frontend `frontend/.env` (shared for local + production frontend base path)

## Critical Backend Variables

- Database/Redis:
  - `DATABASE_URL` (or split `DB_*` fields)
  - `REDIS_URL`
- CORS/frontend access:
  - `CORS_ALLOW_ORIGINS` (comma-separated exact origins)
  - `CORS_ALLOW_ORIGIN_REGEX` (optional regex)
  - `CORS_ALLOW_PRIVATE_NETWORK_ORIGINS` (`true` to allow LAN/VM origins like `192.168.x.x`)
- Device:
  - `ZK_DEVICE_IP`, `ZK_DEVICE_PORT`, `ZK_DEVICE_PASSWORD`, `ZK_DEVICE_TIMEOUT_SECONDS`, `ZK_DEVICE_ID`
  - `ZK_OMIT_PING`, `DEVICE_AUTO_SYNC_ENABLED`
- Locale / auth:
  - `TIMEZONE`
  - `AUTH_ENABLED`, `JWT_SECRET_KEY`
- Optional:
  - `XAI_API_KEY`

Device write / correction policy lives in `backend/app/core/device_policy.py` (not `.env`).

## Local Developer Start

```bash
make install
make start
```

## VM Start

```bash
make start-vm
```

1. Deploy DB migrations (`alembic upgrade head`)
2. Deploy backend API
3. Deploy Celery worker and beat
4. Deploy frontend with correct `VITE_API_URL`
5. Validate:
   - `/health`
   - `/health/db`
   - `/health/redis`
   - `/health/devices`
   - `/health/queue`
   - `/ops/metrics`

## VM/LAN CORS Notes

- If frontend is served from a VM/LAN IP (`http://192.168.x.x:5173`), keep `CORS_ALLOW_PRIVATE_NETWORK_ORIGINS=true` or add that exact frontend origin to `CORS_ALLOW_ORIGINS`.
- `start-vm.js` now auto-injects VM frontend origin into backend CORS origins unless you explicitly set `CORS_ALLOW_ORIGINS`.

## Reverse Proxy Contract (Nginx)

Use `/api` as the only frontend API base path.

```nginx
server {
    listen 80;
    server_name 192.168.1.117;

    root /var/www/biometric-frontend/dist;
    index index.html;

    location / {
        try_files $uri /index.html;
    }

    # IMPORTANT: trailing slash in both location and proxy_pass rewrites /api/* -> /* upstream.
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Without the trailing-slash rewrite form above, upstream receives `/api/auth/login` instead of `/auth/login`.

## Production Safety Checklist

- strong `JWT_SECRET_KEY`
- auth bootstrap credentials removed after first admin setup
- set `DEVICE_WRITES_ENABLED = False` in `backend/app/core/device_policy.py` during initial cutover
- firmware certification rows seeded and reviewed
- dashboards and alerts verified before enabling writes
