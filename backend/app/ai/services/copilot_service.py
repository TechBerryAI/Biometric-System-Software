"""Safe conversational analytics foundation with controlled intents."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.cache.redis_cache import AIResponseCache
from app.ai.prompts.copilot import COPILOT_EXPLANATION_SYSTEM_PROMPT
from app.ai.providers import AIProviderError, AIUsage, GrokProvider
from app.ai.schemas.insight_models import (
    AIUsageInfo,
    CopilotExplanationLLMOutput,
    CopilotIntent,
    CopilotQueryRequest,
    CopilotQueryResponse,
)
from app.core.config import Settings
from app.models.attendance_session import AttendanceSession
from app.models.employee import Employee
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


class CopilotService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = GrokProvider(settings)
        self._cache = AIResponseCache(settings)

    def answer(self, db: Session, req: CopilotQueryRequest) -> CopilotQueryResponse:
        intent, confidence = self._parse_intent(req.question)
        if intent == CopilotIntent.unsupported:
            return CopilotQueryResponse(
                intent=intent,
                intent_confidence=confidence,
                structured_result={},
                blocked=True,
                block_reason="Unsupported question. Allowed intents are absenteeism, attendance trend, and overtime.",
            )

        if intent == CopilotIntent.highest_absenteeism_department:
            result = self._query_highest_absenteeism_department(db)
        elif intent == CopilotIntent.attendance_trend:
            result = self._query_attendance_trend(db, req.question)
        else:
            result = self._query_top_overtime(db)

        digest = hashlib.sha256(str(result).encode("utf-8")).hexdigest()
        cache_key = f"ai:copilot:{intent.value}:{digest}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            explanation = CopilotExplanationLLMOutput.model_validate(cached)
            return CopilotQueryResponse(
                intent=intent,
                intent_confidence=confidence,
                structured_result=result,
                explanation=explanation,
                cached=True,
            )

        usage: AIUsage | None = None
        explanation: CopilotExplanationLLMOutput | None = None
        if self._settings.xai_api_key:
            safe_payload = {
                "intent": intent.value,
                "result": self._safe_result_for_llm(result),
            }
            try:
                explanation, usage = self._provider.complete_json(
                    system_prompt=COPILOT_EXPLANATION_SYSTEM_PROMPT,
                    user_payload=safe_payload,
                    response_model=CopilotExplanationLLMOutput,
                    purpose=f"copilot_{intent.value}",
                    temperature=0.2,
                )
                self._cache.set_json(cache_key, explanation.model_dump(mode="json"))
            except AIProviderError:
                explanation = None

        return CopilotQueryResponse(
            intent=intent,
            intent_confidence=confidence,
            structured_result=result,
            explanation=explanation,
            usage=_usage_to_schema(usage),
            cached=False,
        )

    def _parse_intent(self, text: str) -> tuple[CopilotIntent, str]:
        t = text.lower()
        if "department" in t and ("absent" in t or "absenteeism" in t):
            return CopilotIntent.highest_absenteeism_department, "high"
        if "department" in t and ("late" in t or "lateness" in t):
            return CopilotIntent.unsupported, "low"
        if "trend" in t or "last 30 days" in t or "last 14 days" in t:
            return CopilotIntent.attendance_trend, "high"
        if "overtime" in t or "worked most" in t:
            return CopilotIntent.top_overtime_employees, "medium"
        return CopilotIntent.unsupported, "low"

    def _query_highest_absenteeism_department(self, db: Session) -> dict[str, Any]:
        context = build_management_insight_context(db, self._settings, trend_days=14)
        depts = context.get("department_today", [])
        if not isinstance(depts, list):
            return {"department": None, "absenteeism_percent": 0.0, "sample_size": 0}
        enriched = []
        for item in depts:
            if not isinstance(item, dict):
                continue
            registered = int(item.get("registered", 0) or 0)
            present = int(item.get("present", 0) or 0)
            absent = max(registered - present, 0)
            rate = (absent / registered * 100.0) if registered else 0.0
            enriched.append({"department": item.get("department"), "absenteeism_percent": round(rate, 2), "sample_size": registered})
        enriched.sort(key=lambda x: x["absenteeism_percent"], reverse=True)
        return {"top_department": enriched[0] if enriched else None, "departments": enriched}

    def _query_attendance_trend(self, db: Session, question: str) -> dict[str, Any]:
        days = 30 if "30" in question else 14
        context = build_management_insight_context(db, self._settings, trend_days=days)
        trend = context.get("daily_trend", [])
        if not isinstance(trend, list):
            trend = []
        return {"days": days, "trend": trend}

    def _query_top_overtime(self, db: Session) -> dict[str, Any]:
        tz = ZoneInfo(self._settings.timezone)
        today = datetime.now(tz).date()
        week_start = today - timedelta(days=6)
        start_ts = datetime.combine(week_start, datetime.min.time(), tzinfo=tz).astimezone(ZoneInfo("UTC"))
        stmt = (
            select(
                AttendanceSession.employee_id,
                Employee.name,
                func.sum(AttendanceSession.work_duration).label("total_work_minutes"),
            )
            .join(Employee, Employee.id == AttendanceSession.employee_id)
            .where(AttendanceSession.check_in >= start_ts)
            .group_by(AttendanceSession.employee_id, Employee.name)
            .order_by(func.sum(AttendanceSession.work_duration).desc())
            .limit(5)
        )
        rows = db.execute(stmt).all()
        top = [
            {
                "employee_id": int(row.employee_id),
                "employee_name": str(row.name),
                "total_work_minutes": int(row.total_work_minutes or 0),
            }
            for row in rows
        ]
        return {"week_start": week_start.isoformat(), "week_end": today.isoformat(), "top_overtime": top}

    def _safe_result_for_llm(self, result: dict[str, Any]) -> dict[str, Any]:
        if "top_overtime" in result:
            out = []
            for i, row in enumerate(result["top_overtime"], start=1):
                out.append({"rank": i, "total_work_minutes": row.get("total_work_minutes", 0)})
            return {"week_start": result.get("week_start"), "week_end": result.get("week_end"), "top_overtime": out}
        return result

