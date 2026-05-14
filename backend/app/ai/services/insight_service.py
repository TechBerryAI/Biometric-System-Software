"""Management insight orchestration (context, cache, provider, telemetry)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.ai.cache.redis_cache import AIResponseCache
from app.ai.prompts.management import MANAGEMENT_SYSTEM_PROMPT
from app.ai.providers import AIProviderError, AIUsage, GrokProvider
from app.ai.schemas.insight_models import AIUsageInfo, ManagementInsightsLLMOutput, ManagementInsightsResponse
from app.core.config import Settings
from app.services.management_insight_context import build_management_insight_context

log = logging.getLogger(__name__)


def _usage_to_schema(usage: AIUsage | None, *, cached: bool = False) -> AIUsageInfo | None:
    if usage is None:
        return None
    return AIUsageInfo(
        model=usage.model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        latency_ms=usage.latency_ms,
        retries=usage.retries,
        cached=cached or usage.from_cache,
    )


class InsightService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = GrokProvider(settings)
        self._cache = AIResponseCache(settings)

    def get_management_insights(self, db: Session, *, days: int = 14) -> ManagementInsightsResponse:
        if not self._settings.xai_api_key:
            return ManagementInsightsResponse(
                available=False,
                source="unconfigured",
                bullets=[],
                error_code="xai_api_key_missing",
            )

        cache_key = f"ai:management:days:{days}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            try:
                payload = ManagementInsightsLLMOutput.model_validate(cached.get("payload", cached))
                return ManagementInsightsResponse(
                    available=True,
                    source="cache",
                    bullets=payload.bullets,
                    confidence=payload.confidence,
                    risk_flags=payload.risk_flags,
                    cached=True,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("ai.management.cache_parse_failed key=%s error=%s", cache_key, exc)

        context = build_management_insight_context(db, self._settings, trend_days=days)
        try:
            payload, usage = self._provider.complete_json(
                system_prompt=MANAGEMENT_SYSTEM_PROMPT,
                user_payload=context,
                response_model=ManagementInsightsLLMOutput,
                purpose="management_insights",
            )
        except AIProviderError as exc:
            log.warning("ai.management.failed error=%s", exc)
            return ManagementInsightsResponse(
                available=False,
                source="error",
                bullets=[],
                error_code="provider_failure",
            )

        result = ManagementInsightsResponse(
            available=True,
            source="grok",
            bullets=payload.bullets,
            confidence=payload.confidence,
            risk_flags=payload.risk_flags,
            cached=False,
            usage=_usage_to_schema(usage),
        )
        self._cache.set_json(
            cache_key,
            {
                "payload": payload.model_dump(mode="json"),
                "usage": result.usage.model_dump(mode="json") if result.usage else None,
            },
        )
        return result

    def invalidate_management_cache(self) -> None:
        self._cache.delete_prefix("ai:management:")

