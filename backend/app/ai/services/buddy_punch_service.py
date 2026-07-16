"""Detect potential buddy-punching from rapid sequential device punches."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas.insight_models import AnomalySeverity, BuddyPunchAlert, BuddyPunchResponse
from app.core.config import Settings
from app.domains.attendance.models.attendance_log import AttendanceLog


def _severity_from_window(window_seconds: float) -> AnomalySeverity:
    if window_seconds <= 15:
        return AnomalySeverity.critical
    if window_seconds <= 30:
        return AnomalySeverity.high
    if window_seconds <= 60:
        return AnomalySeverity.medium
    return AnomalySeverity.low


class BuddyPunchService:
    def __init__(self, settings: Settings, *, window_seconds: float = 60.0) -> None:
        self._settings = settings
        self._window_seconds = window_seconds

    def detect(self, db: Session, *, lookback_days: int = 14) -> BuddyPunchResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_at = datetime.now(tz)
        start_at = end_at - timedelta(days=max(lookback_days, 1))

        logs = list(
            db.execute(
                select(AttendanceLog)
                .where(
                    AttendanceLog.timestamp >= start_at.astimezone(ZoneInfo("UTC")),
                    AttendanceLog.timestamp <= end_at.astimezone(ZoneInfo("UTC")),
                )
                .order_by(AttendanceLog.device_id, AttendanceLog.timestamp)
            ).scalars().all()
        )

        alerts: list[BuddyPunchAlert] = []
        by_device: dict[str, list[AttendanceLog]] = {}
        for log in logs:
            by_device.setdefault(log.device_id, []).append(log)

        for device_id, device_logs in by_device.items():
            for i in range(len(device_logs) - 1):
                left = device_logs[i]
                right = device_logs[i + 1]
                if left.employee_code == right.employee_code:
                    continue
                delta = abs((right.timestamp - left.timestamp).total_seconds())
                if delta > self._window_seconds:
                    continue
                severity = _severity_from_window(delta)
                alert_key = hashlib.sha256(
                    f"{device_id}:{left.employee_code}:{right.employee_code}:{left.timestamp.isoformat()}".encode()
                ).hexdigest()[:16]
                alerts.append(
                    BuddyPunchAlert(
                        alert_key=alert_key,
                        detected_at=max(left.timestamp, right.timestamp).astimezone(tz),
                        device_id=device_id,
                        employee_codes=[left.employee_code, right.employee_code],
                        window_seconds=round(delta, 2),
                        severity=severity,
                        description="Two different employees punched the same device within a short interval.",
                        metadata={
                            "first_punch_at": left.timestamp.isoformat(),
                            "second_punch_at": right.timestamp.isoformat(),
                        },
                    )
                )

        alerts.sort(key=lambda item: item.detected_at, reverse=True)
        return BuddyPunchResponse(
            lookback_days=lookback_days,
            generated_at=end_at,
            alerts=alerts,
        )
