"""Redis sliding-window rate limiter for HTTP APIs."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.core.redis_client import redis_client_options
from app.core.redis_keys import with_namespace

RateLimitHandler = Callable[[Request], Awaitable[Response]]

# After a Redis error, skip limiting for a while instead of paying a timeout on every request.
_REDIS_ERROR_BACKOFF_SECONDS = 15.0


class RateLimiter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis: Redis | None = None
        self._skip_until = 0.0
        try:
            self._redis = Redis.from_url(
                str(self._settings.redis_url),
                decode_responses=True,
                **redis_client_options(connect_timeout=1, socket_timeout=1),
            )
        except Exception:  # noqa: BLE001
            self._redis = None

    def _key(self, client_id: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"rate:api:{client_id}")

    def is_allowed(self, client_id: str) -> tuple[bool, int]:
        if self._redis is None or time.monotonic() < self._skip_until:
            return True, 0

        limit = self._settings.api_rate_limit_max
        window = self._settings.api_rate_limit_window_seconds
        now = time.time()
        window_start = now - window
        key = self._key(client_id)
        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            member = f"{now}:{time.time_ns()}"
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, window + 1)
            _, _, count, _ = pipe.execute()
            if int(count) > limit:
                return False, window
            return True, 0
        except (RedisError, OSError, TimeoutError):
            self._skip_until = time.monotonic() + _REDIS_ERROR_BACKOFF_SECONDS
            return True, 0


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Process-wide limiter so every request reuses one Redis connection pool.

    Rebuilt only if the cached settings object is replaced (tests that clear get_settings).
    """
    global _limiter
    settings = get_settings()
    if _limiter is None or _limiter._settings is not settings:  # noqa: SLF001
        _limiter = RateLimiter(settings)
    return _limiter


def reset_rate_limiter() -> None:
    global _limiter
    _limiter = None


def rate_limit_client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_exempt(path: str) -> bool:
    return path.startswith("/health")


async def rate_limit_middleware(request: Request, call_next: RateLimitHandler) -> Response:
    if request.method == "OPTIONS" or _is_exempt(request.url.path):
        return await call_next(request)

    # Redis I/O is blocking; keep it off the event loop so one slow call cannot stall every request.
    allowed, retry_after = await run_in_threadpool(get_rate_limiter().is_allowed, rate_limit_client_id(request))
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
