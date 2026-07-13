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
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.api.attendance import router as attendance_router
from app.api.attendance_correction import router as attendance_correction_router
from app.api.auth import router as auth_router
from app.api.employee import router as employee_router
from app.api.forensics import router as forensics_router
from app.api.insights import router as insights_router
from app.api.operations import router as operations_router
from app.api.sync import router as sync_router
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_sync_event import DeviceSyncEvent
from app.models.reconciliation_job import ReconciliationJob
from app.services.device_service import DeviceService
from app.services.device_registry_service import ensure_default_device, update_device_health

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

cors_origin_patterns: list[str] = []
if settings.cors_allow_origin_regex:
    cors_origin_patterns.append(settings.cors_allow_origin_regex)

if settings.cors_allow_private_network_origins:
    # Support VM/LAN app access (10.x, 172.16-31.x, 192.168.x) without manual code changes.
    cors_origin_patterns.append(r"^https?://((10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$")

combined_cors_origin_regex = "|".join(f"(?:{pattern})" for pattern in cors_origin_patterns) or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=combined_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employee_router)
app.include_router(attendance_router)
app.include_router(attendance_correction_router)
app.include_router(insights_router)
app.include_router(sync_router)
app.include_router(auth_router)
app.include_router(operations_router)
app.include_router(forensics_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "device_read_only": "true" if settings.device_read_only else "false",
    }


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
    fingerprint = device.detect_firmware_fingerprint()
    status = "ONLINE" if ok else "OFFLINE"
    update_device_health(db, status=status, detail=detail, settings=settings)
    registered = ensure_default_device(db, settings=settings)
    registered.firmware_version = fingerprint.get("firmware_version")
    registered.serial_number = fingerprint.get("serial_number")
    registered.capabilities = {"platform": fingerprint.get("platform"), "supports_user_write": True}
    db.commit()
    failing_devices = (
        db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one()
        or 0
    )
    return {
        "status": "ok" if ok else "degraded",
        "detail": detail,
        "failing_devices": int(failing_devices),
        "firmware_version": fingerprint.get("firmware_version"),
        "device_mode": registered.mode,
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
                        DeviceCommandStatus.RETRYING.value,
                        DeviceCommandStatus.VERIFYING.value,
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
                DeviceCommand.status.in_([DeviceCommandStatus.RUNNING.value, DeviceCommandStatus.VERIFYING.value]),
                or_(
                    DeviceCommand.heartbeat_at < stale_cutoff,
                    and_(DeviceCommand.heartbeat_at.is_(None), DeviceCommand.started_at < stale_cutoff),
                ),
            )
        ).scalar_one()
        or 0
    )
    dead_letter = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one()
        or 0
    )
    verification_failures = (
        db.execute(select(func.count()).where(DeviceCommand.verification_status == "FAILED")).scalar_one() or 0
    )
    reconciliation_pending = (
        db.execute(select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "RUNNING"]))).scalar_one() or 0
    )
    lock_contention = (
        db.execute(select(func.count()).where(DeviceSyncEvent.event_type == "LOCK_CONTENTION")).scalar_one() or 0
    )
    return {
        "queue_depth": int(queue_depth),
        "stale_commands": int(stale_commands),
        "dead_letter_commands": int(dead_letter),
        "verification_failures": int(verification_failures),
        "reconciliation_pending": int(reconciliation_pending),
        "lock_contention_events": int(lock_contention),
    }


@app.get("/health/reconciliation", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def health_reconciliation(db: Session = Depends(get_db)) -> dict[str, int]:
    pending = (
        db.execute(select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "RUNNING", "REVIEW_REQUIRED"]))).scalar_one()
        or 0
    )
    completed = db.execute(select(func.count()).where(ReconciliationJob.status == "COMPLETED")).scalar_one() or 0
    return {
        "pending_jobs": int(pending),
        "completed_jobs": int(completed),
    }


