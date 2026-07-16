"""Dashboard KPI aggregation (single round-trip friendly endpoint)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import RedisCache, get_cache
from app.core.config import Settings, get_settings
from app.core.feature_flags import get_feature_flags
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_user_drift import DeviceUserDrift
from app.domains.employees.models.employee import Employee


class DashboardKpis(BaseModel):
    generated_at: datetime
    period_start: date
    period_end: date
    active_employees: int = 0
    punches_today: int = 0
    punches_period: int = 0
    devices_online: int = 0
    devices_total: int = 0
    open_drift_count: int = 0
    cache_hit: bool = False


class DashboardService:
    def __init__(self, settings: Settings | None = None, cache: RedisCache | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache = cache or get_cache(self._settings)

    def get_kpis(
        self,
        db: Session,
        *,
        days: int = 7,
        tenant_id: int | None = None,
        use_cache: bool = True,
    ) -> DashboardKpis:
        flags = get_feature_flags(self._settings)
        cache_enabled = use_cache and flags.is_enabled("dashboard_cache", db=db, tenant_id=tenant_id)
        cache_key = f"dashboard:kpis:d{days}"
        if cache_enabled:
            cached = self._cache.get_json(cache_key, tenant_id=tenant_id)
            if cached:
                cached["cache_hit"] = True
                return DashboardKpis.model_validate(cached)

        tz = ZoneInfo(self._settings.timezone)
        now = datetime.now(tz)
        end_day = now.date()
        start_day = end_day - timedelta(days=max(days - 1, 0))
        today_start = datetime.combine(end_day, datetime.min.time(), tzinfo=tz).astimezone(ZoneInfo("UTC"))
        period_start = datetime.combine(start_day, datetime.min.time(), tzinfo=tz).astimezone(ZoneInfo("UTC"))
        period_end = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(
            ZoneInfo("UTC")
        )

        active_employees = db.execute(
            select(func.count()).select_from(Employee).where(Employee.departed_at.is_(None))
        ).scalar_one()
        punches_today = db.execute(
            select(func.count())
            .select_from(AttendanceLog)
            .where(AttendanceLog.timestamp >= today_start, AttendanceLog.timestamp < period_end)
        ).scalar_one()
        punches_period = db.execute(
            select(func.count())
            .select_from(AttendanceLog)
            .where(AttendanceLog.timestamp >= period_start, AttendanceLog.timestamp < period_end)
        ).scalar_one()
        devices_total = db.execute(
            select(func.count()).select_from(Device).where(Device.active.is_(True))
        ).scalar_one()
        devices_online = db.execute(
            select(func.count())
            .select_from(Device)
            .where(
                Device.active.is_(True),
                func.upper(Device.health_status).in_(["ONLINE", "OK", "HEALTHY"]),
            )
        ).scalar_one()
        open_drift = db.execute(
            select(func.count()).select_from(DeviceUserDrift).where(DeviceUserDrift.status == "open")
        ).scalar_one()

        payload = DashboardKpis(
            generated_at=now,
            period_start=start_day,
            period_end=end_day,
            active_employees=int(active_employees or 0),
            punches_today=int(punches_today or 0),
            punches_period=int(punches_period or 0),
            devices_online=int(devices_online or 0),
            devices_total=int(devices_total or 0),
            open_drift_count=int(open_drift or 0),
            cache_hit=False,
        )
        if cache_enabled:
            self._cache.set_json(cache_key, payload.model_dump(mode="json"), tenant_id=tenant_id)
        return payload
