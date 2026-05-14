"""Executive reporting service using deterministic context + Grok summarization."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai.cache.redis_cache import AIResponseCache
from app.ai.prompts.reporting import REPORTING_SYSTEM_PROMPT
from app.ai.providers import AIProviderError, AIUsage, GrokProvider
from app.ai.schemas.insight_models import AIUsageInfo, ExecutiveReportLLMOutput, ExecutiveReportResponse
from app.ai.services.anomaly_service import AnomalyService
from app.ai.services.forecasting_service import ForecastingService
from app.core.config import Settings
from app.services.management_insight_context import build_management_insight_context


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


class ReportingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = GrokProvider(settings)
        self._cache = AIResponseCache(settings)
        self._anomalies = AnomalyService(settings)
        self._forecast = ForecastingService(settings)

    def generate_report(
        self,
        db: Session,
        *,
        report_type: Literal["weekly", "monthly", "department"],
        department: str | None = None,
    ) -> ExecutiveReportResponse:
        tz = ZoneInfo(self._settings.timezone)
        today = datetime.now(tz).date()
        lookback = 7 if report_type == "weekly" else 30
        if report_type == "department":
            lookback = 30
        period_start = today - timedelta(days=lookback - 1)
        period_end = today

        scope = department or "all_departments"
        cache_key = f"ai:report:{report_type}:{scope}:{period_start.isoformat()}:{period_end.isoformat()}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            payload = ExecutiveReportLLMOutput.model_validate(cached["report"])
            return ExecutiveReportResponse(
                report_type=report_type,
                generated_at=datetime.now(tz),
                period_start=period_start,
                period_end=period_end,
                scope=scope,
                cached=True,
                usage=None,
                report=payload,
            )

        context = build_management_insight_context(db, self._settings, trend_days=lookback)
        anomalies = self._anomalies.detect_and_explain(db, lookback_days=min(lookback, 30))
        forecast = self._forecast.forecast(db, lookback_days=lookback, horizon_days=7)
        payload = {
            "report_type": report_type,
            "scope": scope,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "attendance_context": context,
            "anomalies": [a.model_dump(mode="json") for a in anomalies.anomalies],
            "forecast": forecast.model_dump(mode="json"),
        }

        usage: AIUsage | None = None
        if self._settings.xai_api_key:
            try:
                report, usage = self._provider.complete_json(
                    system_prompt=REPORTING_SYSTEM_PROMPT,
                    user_payload=payload,
                    response_model=ExecutiveReportLLMOutput,
                    purpose=f"executive_report_{report_type}",
                )
            except AIProviderError:
                report = self._fallback_report(payload)
        else:
            report = self._fallback_report(payload)

        response = ExecutiveReportResponse(
            report_type=report_type,
            generated_at=datetime.now(tz),
            period_start=period_start,
            period_end=period_end,
            scope=scope,
            cached=False,
            usage=_usage_to_schema(usage),
            report=report,
        )
        self._cache.set_json(cache_key, response.model_dump(mode="json"))
        return response

    def _fallback_report(self, payload: dict[str, object]) -> ExecutiveReportLLMOutput:
        context = payload["attendance_context"] if isinstance(payload.get("attendance_context"), dict) else {}
        trend = context.get("daily_trend", []) if isinstance(context, dict) else []
        points = len(trend) if isinstance(trend, list) else 0
        return ExecutiveReportLLMOutput(
            headline="Attendance summary generated without external AI.",
            key_points=[
                f"Summary window includes {points} day(s) of aggregate attendance data.",
                "Deterministic anomaly detection has been applied for this period.",
            ],
            risk_items=["External AI provider unavailable; narrative is deterministic fallback."],
            actions=[
                "Review anomaly list and verify shift schedules for flagged days.",
                "Re-run report after AI connectivity is restored for richer narrative.",
            ],
            markdown=(
                "## Executive Attendance Summary\n"
                "- AI narrative unavailable; using deterministic summary.\n"
                "- Attendance trends and anomaly flags remain fully available.\n"
            ),
            narrative_blocks=[
                {
                    "title": "Operational Overview",
                    "body": "This report was generated from aggregate attendance and anomaly metrics without external narration.",
                }
            ],
        )

