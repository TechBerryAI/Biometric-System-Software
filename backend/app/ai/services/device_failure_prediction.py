"""Predict device failure risk from health signals and command history."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas.insight_models import DeviceFailurePredictionResponse, DeviceFailureRisk
from app.core.config import Settings
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus


class DeviceFailurePredictionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def predict(self, db: Session) -> DeviceFailurePredictionResponse:
        tz = ZoneInfo(self._settings.timezone)
        generated_at = datetime.now(tz)
        stale_threshold = generated_at - timedelta(hours=6)

        devices = list(db.execute(select(Device).where(Device.active.is_(True))).scalars().all())
        risks: list[DeviceFailureRisk] = []

        for device in devices:
            score = 0.0
            factors: list[str] = []
            window_hours: int | None = None

            if device.health_status in {"OFFLINE", "DEGRADED", "UNKNOWN"}:
                score += 35.0
                factors.append(f"health_status={device.health_status}")

            if device.last_seen is None or device.last_seen < stale_threshold:
                score += 30.0
                factors.append("stale_last_seen")
                window_hours = 24

            failed_count = db.execute(
                select(func.count())
                .select_from(DeviceCommand)
                .where(
                    DeviceCommand.device_id == device.name,
                    DeviceCommand.status.in_(
                        [
                            DeviceCommandStatus.FAILED.value,
                            DeviceCommandStatus.DEAD_LETTER.value,
                            DeviceCommandStatus.RECONCILIATION_REQUIRED.value,
                        ]
                    ),
                    DeviceCommand.created_at >= generated_at - timedelta(days=7),
                )
            ).scalar_one()
            if failed_count:
                score += min(float(failed_count) * 8.0, 35.0)
                factors.append(f"recent_failed_commands={failed_count}")
                window_hours = window_hours or 72

            if device.mode != "NORMAL":
                score += 10.0
                factors.append(f"mode={device.mode}")

            score = min(score, 100.0)
            risk_level = self._risk_level(score)
            if score >= 20.0:
                risks.append(
                    DeviceFailureRisk(
                        device_uuid=device.device_uuid,
                        device_name=device.name,
                        risk_score=round(score, 2),
                        risk_level=risk_level,
                        factors=factors,
                        predicted_failure_window_hours=window_hours,
                    )
                )

        risks.sort(key=lambda item: item.risk_score, reverse=True)
        return DeviceFailurePredictionResponse(generated_at=generated_at, devices=risks)

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= 75:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 30:
            return "medium"
        return "low"
