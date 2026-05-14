"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.attendance import router as attendance_router
from app.api.auth import router as auth_router
from app.api.employee import router as employee_router
from app.api.insights import router as insights_router
from app.api.operations import router as operations_router
from app.api.sync import router as sync_router
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.services.device_service import DeviceService
from app.services.device_registry_service import update_device_health

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan, debug=settings.debug)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    started = datetime.now(ZoneInfo("UTC"))
    response = await call_next(request)
    elapsed_ms = int((datetime.now(ZoneInfo("UTC")) - started).total_seconds() * 1000)
    response.headers["x-request-id"] = request_id
    logging.getLogger("http.request").info(
        '{"request_id":"%s","method":"%s","path":"%s","status_code":%s,"duration_ms":%s}',
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://frontend:5173",
    ],
    # Allow Vite fallback ports (5174, 5175, ...) during local development.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employee_router)
app.include_router(attendance_router)
app.include_router(insights_router)
app.include_router(sync_router)
app.include_router(auth_router)
app.include_router(operations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/db", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/health/redis", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_redis() -> dict[str, str]:
    client = Redis.from_url(str(settings.redis_url), socket_timeout=3, socket_connect_timeout=3)
    client.ping()
    return {"status": "ok"}


@app.get("/health/devices", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_devices(db: Session = Depends(get_db)) -> dict[str, object]:
    device = DeviceService(settings=settings)
    ok, detail = device.check_connection()
    status = "ONLINE" if ok else "OFFLINE"
    update_device_health(db, status=status, detail=detail, settings=settings)
    db.commit()
    failing_devices = (
        db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one()
        or 0
    )
    return {
        "status": "ok" if ok else "degraded",
        "detail": detail,
        "failing_devices": int(failing_devices),
    }


@app.get("/health/ai", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_ai() -> dict[str, str]:
    if not settings.xai_api_key:
        return {"status": "degraded", "detail": "XAI_API_KEY not configured"}
    return {"status": "ok"}


@app.get("/health/queue", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_queue(db: Session = Depends(get_db)) -> dict[str, int]:
    stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=settings.command_stale_minutes)
    queue_depth = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status.in_(
                    [
                        DeviceCommandStatus.PENDING.value,
                        DeviceCommandStatus.RUNNING.value,
                        DeviceCommandStatus.FAILED.value,
                    ]
                )
            )
        ).scalar_one()
        or 0
    )
    stale_commands = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status == DeviceCommandStatus.RUNNING.value,
                DeviceCommand.started_at < stale_cutoff,
            )
        ).scalar_one()
        or 0
    )
    return {
        "queue_depth": int(queue_depth),
        "stale_commands": int(stale_commands),
    }


