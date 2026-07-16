"""Management insight orchestration (context, cache, provider, telemetry)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.cache.redis_cache import AIResponseCache
from app.ai.prompts.management import MANAGEMENT_SYSTEM_PROMPT
from app.ai.prompts.payroll import PAYROLL_INSIGHTS_SYSTEM_PROMPT
from app.ai.providers import AIProviderError, AIUsage, GrokProvider
from app.ai.schemas.insight_models import (
    AIUsageInfo,
    AnomalySeverity,
    ManagementInsightsLLMOutput,
    ManagementInsightsResponse,
    PayrollInsightItem,
    PayrollInsightsLLMOutput,
    PayrollInsightsResponse,
)
from app.core.config import Settings
from app.ai.services.management_insight_context import build_management_insight_context
from app.domains.attendance.services.daily_summary_service import compute_daily_summaries_range
from app.domains.employees.models.employee import Employee

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

    def get_payroll_insights(self, db: Session, *, days: int = 14) -> PayrollInsightsResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(days - 1, 1))

        context = self._build_payroll_context(db, start_day=start_day, end_day=end_day)
        if not self._settings.xai_api_key:
            return PayrollInsightsResponse(
                period_start=start_day,
                period_end=end_day,
                available=True,
                source="rules",
                insights=self._rules_payroll_insights(context),
                confidence="medium",
            )

        cache_key = f"ai:payroll:days:{days}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            try:
                payload = PayrollInsightsLLMOutput.model_validate(cached.get("payload", cached))
                return PayrollInsightsResponse(
                    period_start=start_day,
                    period_end=end_day,
                    available=True,
                    source="cache",
                    insights=payload.insights,
                    confidence=payload.confidence,
                    cached=True,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("ai.payroll.cache_parse_failed key=%s error=%s", cache_key, exc)

        try:
            payload, usage = self._provider.complete_json(
                system_prompt=PAYROLL_INSIGHTS_SYSTEM_PROMPT,
                user_payload=context,
                response_model=PayrollInsightsLLMOutput,
                purpose="payroll_insights",
            )
        except AIProviderError as exc:
            log.warning("ai.payroll.failed error=%s", exc)
            return PayrollInsightsResponse(
                period_start=start_day,
                period_end=end_day,
                available=True,
                source="rules",
                insights=self._rules_payroll_insights(context),
                confidence="medium",
                error_code="provider_failure",
            )

        result = PayrollInsightsResponse(
            period_start=start_day,
            period_end=end_day,
            available=True,
            source="grok",
            insights=payload.insights,
            confidence=payload.confidence,
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

    def _build_payroll_context(self, db: Session, *, start_day: date, end_day: date) -> dict[str, Any]:
        summaries_by_day = compute_daily_summaries_range(db, start_day, end_day, self._settings)
        employees = list(db.execute(select(Employee)).scalars().all())
        headcount = len(employees)

        missing_checkout = 0
        overtime_days = 0
        incomplete_days = 0
        total_work_minutes = 0
        work_samples = 0

        for day_rows in summaries_by_day.values():
            for row in day_rows:
                if row.first_check_in is None:
                    continue
                if row.last_check_out is None:
                    missing_checkout += 1
                if row.total_work_minutes is not None:
                    total_work_minutes += row.total_work_minutes
                    work_samples += 1
                    if row.total_work_minutes >= 10 * 60:
                        overtime_days += 1
                if row.first_check_in is not None and row.last_check_out is None:
                    incomplete_days += 1

        avg_work = (total_work_minutes / work_samples) if work_samples else 0.0
        return {
            "period_start": start_day.isoformat(),
            "period_end": end_day.isoformat(),
            "headcount": headcount,
            "missing_checkout_count": missing_checkout,
            "incomplete_day_count": incomplete_days,
            "overtime_day_count": overtime_days,
            "avg_work_minutes": round(avg_work, 2),
        }

    def _rules_payroll_insights(self, context: dict[str, Any]) -> list[PayrollInsightItem]:
        insights: list[PayrollInsightItem] = []
        missing = int(context.get("missing_checkout_count", 0))
        incomplete = int(context.get("incomplete_day_count", 0))
        overtime = int(context.get("overtime_day_count", 0))

        if missing > 0:
            insights.append(
                PayrollInsightItem(
                    key="missing_checkouts",
                    title="Missing check-outs affect payroll hours",
                    detail=f"{missing} punch sessions lack a matching check-out in the selected window.",
                    severity=AnomalySeverity.high if missing >= 5 else AnomalySeverity.medium,
                    metric_value=float(missing),
                )
            )
        if incomplete > 0:
            insights.append(
                PayrollInsightItem(
                    key="incomplete_days",
                    title="Incomplete attendance days",
                    detail=f"{incomplete} employee-days have check-in without closure; verify before payroll export.",
                    severity=AnomalySeverity.medium,
                    metric_value=float(incomplete),
                )
            )
        if overtime > 0:
            insights.append(
                PayrollInsightItem(
                    key="overtime_exposure",
                    title="Extended work sessions detected",
                    detail=f"{overtime} sessions exceed 10 hours; review overtime policy before payroll run.",
                    severity=AnomalySeverity.high if overtime >= 3 else AnomalySeverity.low,
                    metric_value=float(overtime),
                )
            )
        if not insights:
            insights.append(
                PayrollInsightItem(
                    key="payroll_ready",
                    title="Payroll signals look stable",
                    detail="No major missing checkout or overtime anomalies detected in the selected window.",
                    severity=AnomalySeverity.low,
                    metric_value=0.0,
                )
            )
        return insights

