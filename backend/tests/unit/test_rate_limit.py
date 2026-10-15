"""Unit tests for API rate limiting."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.rate_limit import RateLimiter, rate_limit_client_id


class _FakeRequest:
    def __init__(self, *, host: str = "127.0.0.1", forwarded: str | None = None) -> None:
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        self.client = MagicMock()
        self.client.host = host


@pytest.mark.testid("BE-UNIT-RATE-001")
def test_rate_limit_client_id_prefers_forwarded_header() -> None:
    request = _FakeRequest(host="10.0.0.1", forwarded="203.0.113.10, 10.0.0.1")
    assert rate_limit_client_id(request) == "203.0.113.10"


@pytest.mark.testid("BE-UNIT-RATE-002")
def test_rate_limiter_allows_without_redis() -> None:
    limiter = RateLimiter()
    limiter._redis = None
    allowed, retry_after = limiter.is_allowed("127.0.0.1")
    assert allowed is True
    assert retry_after == 0


@pytest.mark.testid("BE-UNIT-RATE-003")
def test_rate_limiter_blocks_when_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_RATE_LIMIT_MAX", "10")
    monkeypatch.setenv("API_RATE_LIMIT_WINDOW_SECONDS", "60")
    from app.core.config import get_settings

    get_settings.cache_clear()

    limiter = RateLimiter()
    fake_redis = MagicMock()
    fake_pipe = MagicMock()
    fake_pipe.execute.return_value = [None, None, 11, None]
    fake_redis.pipeline.return_value = fake_pipe
    limiter._redis = fake_redis

    allowed, retry_after = limiter.is_allowed("127.0.0.1")
    assert allowed is False
    assert retry_after == 60


@pytest.mark.testid("BE-UNIT-RATE-004")
def test_rate_limiter_backs_off_after_redis_error() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    limiter = RateLimiter()
    fake_redis = MagicMock()
    fake_redis.pipeline.side_effect = RedisConnectionError("down")
    limiter._redis = fake_redis

    assert limiter.is_allowed("10.0.0.5") == (True, 0)
    # Second call inside the backoff window must not touch Redis (no per-request timeout).
    assert limiter.is_allowed("10.0.0.5") == (True, 0)
    assert fake_redis.pipeline.call_count == 1


@pytest.mark.testid("BE-UNIT-RATE-005")
def test_rate_limiter_is_shared_per_process() -> None:
    from app.core.rate_limit import get_rate_limiter, reset_rate_limiter

    reset_rate_limiter()
    try:
        assert get_rate_limiter() is get_rate_limiter()
    finally:
        reset_rate_limiter()
