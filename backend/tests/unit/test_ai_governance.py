"""Unit tests for AI governance rate limits."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.ai.utils.governance import AIGovernance
from app.core.config import get_settings


class _CountingRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, _key: str, _ttl: int) -> bool:
        return True


@pytest.mark.testid("BE-UNIT-AI-GOV-001")
def test_assert_allowed_with_fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _CountingRedis()
    monkeypatch.setattr("app.ai.utils.governance.Redis.from_url", lambda *a, **k: fake)

    gov = AIGovernance(get_settings())
    gov.assert_allowed("user-uuid-1")


@pytest.mark.testid("BE-UNIT-AI-GOV-001")
def test_assert_allowed_degrades_when_redis_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = MagicMock()
    broken.incr.side_effect = OSError("redis down")
    monkeypatch.setattr("app.ai.utils.governance.Redis.from_url", lambda *a, **k: broken)

    gov = AIGovernance(get_settings())
    gov.assert_allowed("user-uuid-2")


@pytest.mark.testid("BE-UNIT-AI-GOV-001")
def test_assert_allowed_raises_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    fake = _CountingRedis()
    monkeypatch.setattr("app.ai.utils.governance.Redis.from_url", lambda *a, **k: fake)

    gov = AIGovernance(settings)
    for _ in range(settings.ai_rate_limit_per_minute):
        gov.assert_allowed("rate-limited-user")
    with pytest.raises(HTTPException) as exc_info:
        gov.assert_allowed("rate-limited-user")
    assert exc_info.value.status_code == 429
