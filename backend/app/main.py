"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.router import router as insights_router
from app.core.config import get_settings
from app.domains.attendance.correction_router import router as attendance_correction_router
from app.domains.attendance.router import router as attendance_router
from app.domains.auth.router import router as auth_router
from app.domains.devices.router import router as sync_router
from app.domains.employees.router import router as employee_router
from app.domains.ops.health import router as health_router
from app.domains.ops.router import router as operations_router

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
app.include_router(health_router)
