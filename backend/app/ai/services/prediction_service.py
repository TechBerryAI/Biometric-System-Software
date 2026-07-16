"""Heuristic attendance and shift prediction from historical summaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai.schemas.insight_models import AttendancePredictionDay, AttendancePredictionResponse
from app.core.config import Settings
from app.domains.attendance.services.daily_summary_service import compute_daily_summaries_range


class PredictionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def predict_attendance(
        self,
        db: Session,
        *,
        history_days: int = 14,
        horizon_days: int = 7,
    ) -> AttendancePredictionResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(history_days - 1, 1))
        generated_at = datetime.now(tz)

        summaries_by_day = compute_daily_summaries_range(db, start_day, end_day, self._settings)
        daily_present: list[int] = []
        daily_absent: list[int] = []
        daily_late: list[int] = []

        current = start_day
        while current <= end_day:
            rows = summaries_by_day.get(current, [])
            present = sum(1 for row in rows if row.first_check_in is not None)
            absent = max(len(rows) - present, 0)
            late = sum(
                1
                for row in rows
                if row.first_check_in is not None and row.first_check_in.astimezone(tz).hour >= 9
                and (row.first_check_in.astimezone(tz).hour > 9 or row.first_check_in.astimezone(tz).minute > 15)
            )
            daily_present.append(present)
            daily_absent.append(absent)
            daily_late.append(late)
            current += timedelta(days=1)

        if sum(daily_present) == 0 or len([value for value in daily_present if value > 0]) < 3:
            return AttendancePredictionResponse(
                period_start=start_day,
                period_end=end_day + timedelta(days=horizon_days),
                generated_at=generated_at,
                horizon_days=horizon_days,
                source="insufficient_data",
                predictions=[],
            )

        avg_present = sum(daily_present) / len(daily_present)
        avg_absent = sum(daily_absent) / len(daily_absent)
        avg_late = sum(daily_late) / len(daily_late)
        confidence: str = "high" if len(daily_present) >= 10 else "medium"

        predictions: list[AttendancePredictionDay] = []
        for offset in range(1, horizon_days + 1):
            target = end_day + timedelta(days=offset)
            weekday = target.weekday()
            weekend_factor = 0.55 if weekday >= 5 else 1.0
            predictions.append(
                AttendancePredictionDay(
                    day=target,
                    predicted_present=max(0, round(avg_present * weekend_factor)),
                    predicted_absent=max(0, round(avg_absent * weekend_factor)),
                    predicted_late=max(0, round(avg_late * weekend_factor)),
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )

        return AttendancePredictionResponse(
            period_start=start_day,
            period_end=end_day + timedelta(days=horizon_days),
            generated_at=generated_at,
            horizon_days=horizon_days,
            source="heuristic",
            predictions=predictions,
        )
