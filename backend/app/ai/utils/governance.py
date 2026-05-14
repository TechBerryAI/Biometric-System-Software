"""AI governance controls: per-user rate limit and daily quota."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace


class AIGovernance:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis = Redis.from_url(
            str(self._settings.redis_url),
            socket_timeout=1,
            socket_connect_timeout=1,
            decode_responses=True,
        )

    def _minute_key(self, user_uuid: str) -> str:
        now = datetime.now(ZoneInfo("UTC"))
        key = f"ai:rl:{user_uuid}:{now.strftime('%Y%m%d%H%M')}"
        return with_namespace(self._settings.redis_namespace, key)

    def _daily_key(self, user_uuid: str) -> str:
        now = datetime.now(ZoneInfo("UTC"))
        key = f"ai:quota:{user_uuid}:{now.strftime('%Y%m%d')}"
        return with_namespace(self._settings.redis_namespace, key)

    def assert_allowed(self, user_uuid: str) -> None:
        try:
            minute_key = self._minute_key(user_uuid)
            daily_key = self._daily_key(user_uuid)
            minute_count = self._redis.incr(minute_key)
            if minute_count <= 1:
                self._redis.expire(minute_key, 120)
            daily_count = self._redis.incr(daily_key)
            if daily_count <= 1:
                self._redis.expire(daily_key, 90000)
        except (RedisError, OSError, TimeoutError):
            # Keep AI endpoints available during transient Redis outages.
            return

        if minute_count > self._settings.ai_rate_limit_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="AI rate limit exceeded")
        if daily_count > self._settings.ai_daily_quota:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="AI daily quota exceeded")
