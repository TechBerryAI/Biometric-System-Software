"""Deterministic attendance forecasting for short operational horizons."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai.schemas.insight_models import ForecastPoint, ForecastResponse
from app.core.config import Settings
from app.services.management_insight_context import build_management_insight_context


def _linear_projection(values: list[float], steps: int) -> list[float]:
    if not values:
        return [0.0 for _ in range(steps)]
    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
    slope = num / den
    start = values[-1]
    return [max(0.0, min(100.0, start + slope * (i + 1))) for i in range(steps)]


class ForecastingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def forecast(self, db: Session, *, lookback_days: int = 30, horizon_days: int = 7) -> ForecastResponse:
        tz = ZoneInfo(self._settings.timezone)
        today = datetime.now(tz).date()
        context = build_management_insight_context(db, self._settings, trend_days=lookback_days)
        trend = context.get("daily_trend", [])

        attendance = [float(x.get("attendance_rate_percent", 0.0)) for x in trend if isinstance(x, dict)]
        absent = [float(x.get("absent", 0.0)) / max(float(x.get("headcount", 1.0)), 1.0) * 100.0 for x in trend if isinstance(x, dict)]

        att_f = _linear_projection(attendance, horizon_days)
        abs_f = _linear_projection(absent, horizon_days)

        points: list[ForecastPoint] = []
        for idx in range(horizon_days):
            points.append(
                ForecastPoint(
                    date=today + timedelta(days=idx + 1),
                    predicted_attendance_rate_percent=round(att_f[idx], 2),
                    predicted_absenteeism_percent=round(abs_f[idx], 2),
                )
            )

        return ForecastResponse(
            generated_at=datetime.now(tz),
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            points=points,
        )

