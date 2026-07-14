"""Deterministic anomaly detection with optional AI explanation."""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.cache.redis_cache import AIResponseCache
from app.ai.prompts.anomaly import ANOMALY_EXPLANATION_SYSTEM_PROMPT
from app.ai.providers import AIProviderError, AIUsage, GrokProvider
from app.ai.schemas.insight_models import (
    AIUsageInfo,
    AnomalyDetectionResponse,
    AnomalyExplanationsLLMOutput,
    AnomalySeverity,
    AttendanceAnomalyRead,
)
from app.core.config import Settings
from app.domains.attendance.models.attendance_session import AttendanceSession
from app.domains.attendance.services.daily_summary_service import compute_daily_summaries_range

log = logging.getLogger(__name__)

try:
    from sklearn.ensemble import IsolationForest  # type: ignore
except Exception:  # noqa: BLE001
    IsolationForest = None  # type: ignore[assignment]


@dataclass
class _DayFeatures:
    day: date
    attendance_rate: float
    avg_work_minutes: float
    missing_checkout_rate: float
    overtime_rate: float
    offhour_checkin_rate: float
    absenteeism_rate: float


def _severity_from_score(score: float) -> AnomalySeverity:
    if score >= 3.0:
        return AnomalySeverity.critical
    if score >= 2.0:
        return AnomalySeverity.high
    if score >= 1.25:
        return AnomalySeverity.medium
    return AnomalySeverity.low


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


class AnomalyService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = GrokProvider(settings)
        self._cache = AIResponseCache(settings)

    def detect_and_explain(self, db: Session, *, lookback_days: int = 30) -> AnomalyDetectionResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(lookback_days - 1, 1))

        rows = self._build_features(db, start_day=start_day, end_day=end_day)
        anomalies, detector = self._detect(rows)

        usage: AIUsage | None = None
        if anomalies:
            anomalies, usage = self._attach_ai_explanations(anomalies)

        return AnomalyDetectionResponse(
            period_start=start_day,
            period_end=end_day,
            generated_at=datetime.now(tz),
            detector=detector,
            anomalies=anomalies,
            usage=_usage_to_schema(usage),
            cached=False,
        )

    def _build_features(self, db: Session, *, start_day: date, end_day: date) -> list[_DayFeatures]:
        out: list[_DayFeatures] = []
        tz = ZoneInfo(self._settings.timezone)
        summaries_by_day = compute_daily_summaries_range(db, start_day, end_day, self._settings)
        current = start_day
        while current <= end_day:
            summary = summaries_by_day.get(current, [])
            headcount = len(summary)
            present = sum(1 for row in summary if row.first_check_in is not None)
            absent = max(headcount - present, 0)
            with_checkout = [
                row
                for row in summary
                if row.first_check_in is not None and row.last_check_out is not None and row.total_work_minutes is not None
            ]
            missing_checkout = sum(1 for row in summary if row.first_check_in is not None and row.last_check_out is None)
            overtime = sum(1 for row in with_checkout if (row.total_work_minutes or 0) >= 10 * 60)

            day_sessions = db.execute(
                select(AttendanceSession).where(
                    AttendanceSession.check_in >= datetime.combine(current, datetime.min.time(), tzinfo=tz).astimezone(
                        ZoneInfo("UTC")
                    ),
                    AttendanceSession.check_in
                    < datetime.combine(current + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(
                        ZoneInfo("UTC")
                    ),
                )
            ).scalars().all()
            offhour = sum(
                1
                for sess in day_sessions
                if sess.check_in.astimezone(tz).hour < 6 or sess.check_in.astimezone(tz).hour >= 22
            )
            session_n = len(day_sessions)

            avg_work = (
                sum(float(row.total_work_minutes or 0) for row in with_checkout) / len(with_checkout)
                if with_checkout
                else 0.0
            )
            out.append(
                _DayFeatures(
                    day=current,
                    attendance_rate=(present / headcount * 100.0) if headcount else 0.0,
                    avg_work_minutes=avg_work,
                    missing_checkout_rate=(missing_checkout / present * 100.0) if present else 0.0,
                    overtime_rate=(overtime / max(len(with_checkout), 1) * 100.0) if with_checkout else 0.0,
                    offhour_checkin_rate=(offhour / session_n * 100.0) if session_n else 0.0,
                    absenteeism_rate=(absent / headcount * 100.0) if headcount else 0.0,
                )
            )
            current += timedelta(days=1)
        return out

    def _detect(self, rows: list[_DayFeatures]) -> tuple[list[AttendanceAnomalyRead], str]:
        if len(rows) < 7:
            return [], "heuristic"

        anomalies: list[AttendanceAnomalyRead] = []
        if IsolationForest is not None and len(rows) >= 10:
            detector = "isolation_forest"
            x = [
                [
                    r.attendance_rate,
                    r.avg_work_minutes,
                    r.missing_checkout_rate,
                    r.overtime_rate,
                    r.offhour_checkin_rate,
                    r.absenteeism_rate,
                ]
                for r in rows
            ]
            model = IsolationForest(contamination=min(max(2.0 / len(rows), 0.05), 0.20), random_state=42)
            preds = model.fit_predict(x)
            scores = (-model.score_samples(x)).tolist()
            for i, (pred, score) in enumerate(zip(preds, scores, strict=True)):
                if pred != -1:
                    continue
                anomalies.extend(self._create_day_anomalies(rows, i, score))
            return anomalies, detector

        detector = "heuristic"
        for i in range(2, len(rows)):
            baseline = rows[max(0, i - 7) : i]
            if not baseline:
                continue
            b_abs = sum(x.absenteeism_rate for x in baseline) / len(baseline)
            b_ot = sum(x.overtime_rate for x in baseline) / len(baseline)
            b_miss = sum(x.missing_checkout_rate for x in baseline) / len(baseline)
            r = rows[i]
            if r.absenteeism_rate > b_abs + 15:
                anomalies.append(
                    self._build_anomaly(r, "absenteeism_spike", r.absenteeism_rate, b_abs, 2.5, "Abnormal absenteeism")
                )
            if r.overtime_rate > b_ot + 18:
                anomalies.append(
                    self._build_anomaly(r, "overtime_spike", r.overtime_rate, b_ot, 2.0, "Excessive overtime share")
                )
            if r.missing_checkout_rate > b_miss + 14:
                anomalies.append(
                    self._build_anomaly(
                        r,
                        "missing_checkout_spike",
                        r.missing_checkout_rate,
                        b_miss,
                        1.9,
                        "Repeated missing check-outs",
                    )
                )
        return anomalies, detector

    def _create_day_anomalies(self, rows: list[_DayFeatures], i: int, score: float) -> list[AttendanceAnomalyRead]:
        baseline = rows[max(0, i - 7) : i]
        if not baseline:
            return []
        r = rows[i]
        avg_abs = sum(x.absenteeism_rate for x in baseline) / len(baseline)
        avg_ot = sum(x.overtime_rate for x in baseline) / len(baseline)
        avg_missing = sum(x.missing_checkout_rate for x in baseline) / len(baseline)
        avg_offhour = sum(x.offhour_checkin_rate for x in baseline) / len(baseline)

        out: list[AttendanceAnomalyRead] = []
        if r.overtime_rate > avg_ot + 10:
            out.append(self._build_anomaly(r, "overtime_spike", r.overtime_rate, avg_ot, score, "Excessive overtime share"))
        if r.offhour_checkin_rate > avg_offhour + 10:
            out.append(
                self._build_anomaly(
                    r,
                    "suspicious_punch_timing",
                    r.offhour_checkin_rate,
                    avg_offhour,
                    score,
                    "Suspicious punch timing (off-hour check-ins)",
                )
            )
        if r.missing_checkout_rate > avg_missing + 8:
            out.append(
                self._build_anomaly(
                    r,
                    "missing_checkout_spike",
                    r.missing_checkout_rate,
                    avg_missing,
                    score,
                    "Repeated missing check-outs",
                )
            )
        if r.absenteeism_rate > avg_abs + 10:
            out.append(
                self._build_anomaly(
                    r,
                    "absenteeism_spike",
                    r.absenteeism_rate,
                    avg_abs,
                    score,
                    "Abnormal absenteeism",
                )
            )
        return out

    def _build_anomaly(
        self,
        row: _DayFeatures,
        key: str,
        value: float,
        baseline: float,
        score: float,
        description: str,
    ) -> AttendanceAnomalyRead:
        severity = _severity_from_score(score)
        return AttendanceAnomalyRead(
            id=0,
            anomaly_key=key,
            anomaly_date=row.day,
            category="attendance",
            severity=severity,
            score=round(float(score), 3),
            department=None,
            metric_value=round(float(value), 3),
            baseline_value=round(float(baseline), 3),
            description=description,
            explanation=None,
            recommendation=None,
            metadata={"unit": "percent", "delta": round(float(value - baseline), 3)},
            created_at=datetime.now(ZoneInfo(self._settings.timezone)),
        )

    def _attach_ai_explanations(
        self,
        anomalies: list[AttendanceAnomalyRead],
    ) -> tuple[list[AttendanceAnomalyRead], AIUsage | None]:
        if not self._settings.xai_api_key:
            return anomalies, None

        anomaly_payload: list[dict[str, Any]] = [
            {
                "anomaly_key": a.anomaly_key,
                "anomaly_date": a.anomaly_date.isoformat(),
                "description": a.description,
                "severity": a.severity.value,
                "metric_value": a.metric_value,
                "baseline_value": a.baseline_value,
                "metadata": a.metadata,
            }
            for a in anomalies
        ]

        digest = hashlib.sha256(str(anomaly_payload).encode("utf-8")).hexdigest()
        cache_key = f"ai:anomaly:explain:{digest}"
        cached = self._cache.get_json(cache_key)
        if cached is not None:
            try:
                out = AnomalyExplanationsLLMOutput.model_validate(cached)
                return self._merge_explanations(anomalies, out), None
            except Exception:  # noqa: BLE001
                pass

        try:
            out, usage = self._provider.complete_json(
                system_prompt=ANOMALY_EXPLANATION_SYSTEM_PROMPT,
                user_payload={"anomalies": anomaly_payload},
                response_model=AnomalyExplanationsLLMOutput,
                purpose="anomaly_explanations",
                temperature=0.2,
                max_tokens=min(self._settings.ai_max_tokens, 900),
            )
        except AIProviderError as exc:
            log.warning("ai.anomaly.explain_failed error=%s", exc)
            return anomalies, None

        self._cache.set_json(cache_key, out.model_dump(mode="json"))
        return self._merge_explanations(anomalies, out), usage

    def _merge_explanations(
        self,
        anomalies: list[AttendanceAnomalyRead],
        output: AnomalyExplanationsLLMOutput,
    ) -> list[AttendanceAnomalyRead]:
        by_key = {item.anomaly_key: item for item in output.items}
        enriched: list[AttendanceAnomalyRead] = []
        for anomaly in anomalies:
            llm = by_key.get(anomaly.anomaly_key)
            if llm is None:
                enriched.append(anomaly)
                continue
            enriched.append(
                anomaly.model_copy(
                    update={
                        "explanation": llm.explanation,
                        "recommendation": llm.recommendation,
                    }
                )
            )
        return enriched

