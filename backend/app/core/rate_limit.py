"""Redis sliding-window rate limiter for HTTP APIs."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace

RateLimitHandler = Callable[[Request], Awaitable[Response]]


class RateLimiter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis: Redis | None = None
        try:
            self._redis = Redis.from_url(
                str(self._settings.redis_url),
                socket_timeout=1,
                socket_connect_timeout=1,
                decode_responses=True,
            )
        except Exception:  # noqa: BLE001
            self._redis = None

    def _key(self, client_id: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"rate:api:{client_id}")

    def is_allowed(self, client_id: str) -> tuple[bool, int]:
        if self._redis is None:
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
            return True, 0


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

    limiter = RateLimiter()
    allowed, retry_after = limiter.is_allowed(rate_limit_client_id(request))
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
