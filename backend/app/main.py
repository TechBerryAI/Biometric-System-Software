"""FastAPI application entrypoint."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.router import router as insights_router
from app.core.config import get_settings
from app.core.config_validation import validate_production_config
from app.core.csrf import csrf_middleware
from app.core.logging_config import configure_logging, get_logger
from app.core.rate_limit import rate_limit_middleware
from app.core.telemetry import setup_telemetry, shutdown_telemetry
from app.core.tenant_middleware import TenantMiddleware
from app.domains.attendance.correction_router import router as attendance_correction_router
from app.domains.attendance.router import router as attendance_router
from app.domains.auth.router import router as auth_router
from app.domains.devices.router import router as sync_router
from app.domains.devices.fleet_router import router as fleet_router
from app.domains.devices.gateway.push_router import router as push_gateway_router
from app.domains.employees.router import router as employee_router
from app.domains.ops.health import router as health_router
from app.domains.ops.metrics_prometheus import setup_prometheus_metrics
from app.domains.ops.router import router as operations_router
from app.domains.reporting.router import router as reporting_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.tenancy.router import router as tenancy_router

settings = get_settings()
configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
validate_production_config(settings)
logger = get_logger("http.request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(app, settings)
    try:
        from app.core.database import SessionLocal
        from app.domains.devices.services.device_registry_service import ensure_default_device

        with SessionLocal() as db:
            ensure_default_device(db, settings)
            db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("device_timezone_bootstrap_failed", exc_info=True)
    logger.info("app_started", service=settings.app_name, environment=settings.environment)
    try:
        yield
    finally:
        # Graceful shutdown: release pooled resources before process exit.
        try:
            from app.domains.devices.gateway.router import reset_device_gateway

            reset_device_gateway()
        except Exception:  # noqa: BLE001
            logger.warning("gateway_shutdown_failed", exc_info=True)
        try:
            from app.core.database import dispose_engines

            dispose_engines()
        except Exception:  # noqa: BLE001
            logger.warning("database_dispose_failed", exc_info=True)
        shutdown_telemetry()
        logger.info("app_stopped", service=settings.app_name)


app = FastAPI(title=settings.app_name, lifespan=lifespan, debug=settings.debug)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    async def csrf_wrapped(req: Request):
        return await csrf_middleware(req, call_next)

    return await rate_limit_middleware(request, csrf_wrapped)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    started = datetime.now(ZoneInfo("UTC"))
    response = await call_next(request)
    elapsed_ms = int((datetime.now(ZoneInfo("UTC")) - started).total_seconds() * 1000)
    response.headers["x-request-id"] = request_id
    logger.info(
        "http_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=elapsed_ms,
    )
    return response

cors_origin_patterns: list[str] = []
if settings.cors_allow_origin_regex:
    cors_origin_patterns.append(settings.cors_allow_origin_regex)

if settings.cors_allow_private_network_origins:
    # Support VM/LAN app access (10.x, 172.16-31.x, 192.168.x) without manual code changes.
    cors_origin_patterns.append(r"^https?://((10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$")

combined_cors_origin_regex = "|".join(f"(?:{pattern})" for pattern in cors_origin_patterns) or None

app.add_middleware(TenantMiddleware)

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
app.include_router(fleet_router)
app.include_router(push_gateway_router)
app.include_router(auth_router)
app.include_router(operations_router)
app.include_router(reporting_router)
app.include_router(dashboard_router)
app.include_router(tenancy_router)
app.include_router(health_router)

setup_prometheus_metrics(app)
