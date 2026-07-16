"""Reporting analytics services."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.daily_summary_service import compute_daily_summaries_range
from app.domains.devices.models.device import Device
from app.domains.employees.models.employee import Employee
from app.domains.reporting.schemas import (
    AttendanceHeatmapResponse,
    BranchComparisonResponse,
    BranchComparisonRow,
    DeviceUptimeResponse,
    DeviceUptimeRow,
    HeatmapCell,
)


class ReportingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def attendance_heatmap(self, db: Session, *, days: int = 14) -> AttendanceHeatmapResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(days - 1, 1))
        generated_at = datetime.now(tz)

        start_utc = datetime.combine(start_day, datetime.min.time(), tzinfo=tz).astimezone(ZoneInfo("UTC"))
        end_utc = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(
            ZoneInfo("UTC")
        )

        logs = db.execute(
            select(AttendanceLog.timestamp).where(
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc,
            )
        ).scalars().all()

        counts: dict[tuple[date, int], int] = defaultdict(int)
        for ts in logs:
            local = ts.astimezone(tz)
            counts[(local.date(), local.hour)] += 1

        cells = [
            HeatmapCell(day=day, hour=hour, punch_count=count)
            for (day, hour), count in sorted(counts.items(), key=lambda item: (item[0][0], item[0][1]))
        ]
        return AttendanceHeatmapResponse(
            period_start=start_day,
            period_end=end_day,
            generated_at=generated_at,
            cells=cells,
        )

    def branch_comparison(self, db: Session, *, days: int = 14) -> BranchComparisonResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(days - 1, 1))
        generated_at = datetime.now(tz)

        employees = list(db.execute(select(Employee)).scalars().all())
        summaries_by_day = compute_daily_summaries_range(db, start_day, end_day, self._settings)

        branch_employees: dict[str, list[Employee]] = defaultdict(list)
        for employee in employees:
            branch_key = (employee.department or "unassigned").strip().lower()
            branch_employees[branch_key].append(employee)

        rows: list[BranchComparisonRow] = []
        for branch_key, branch_emps in sorted(branch_employees.items(), key=lambda item: item[0]):
            emp_ids = {e.id for e in branch_emps}
            present = 0
            late = 0
            work_minutes = 0
            work_samples = 0
            opportunities = 0

            for day_rows in summaries_by_day.values():
                for row in day_rows:
                    if row.employee_id not in emp_ids:
                        continue
                    opportunities += 1
                    if row.first_check_in is not None:
                        present += 1
                        local_hour = row.first_check_in.astimezone(tz).hour
                        if local_hour > 9 or (local_hour == 9 and row.first_check_in.astimezone(tz).minute > 15):
                            late += 1
                    if row.total_work_minutes is not None:
                        work_minutes += row.total_work_minutes
                        work_samples += 1

            headcount = len(branch_emps)
            present_rate = (present / opportunities * 100.0) if opportunities else 0.0
            late_rate = (late / present * 100.0) if present else 0.0
            avg_work_hours = (work_minutes / work_samples / 60.0) if work_samples else 0.0
            rows.append(
                BranchComparisonRow(
                    branch_id=branch_key,
                    branch_name=branch_emps[0].department or "Unassigned",
                    headcount=headcount,
                    present_rate=round(present_rate, 2),
                    late_rate=round(late_rate, 2),
                    avg_work_hours=round(avg_work_hours, 2),
                )
            )

        return BranchComparisonResponse(
            period_start=start_day,
            period_end=end_day,
            generated_at=generated_at,
            branches=rows,
        )

    def device_uptime(self, db: Session, *, days: int = 7) -> DeviceUptimeResponse:
        tz = ZoneInfo(self._settings.timezone)
        end_day = datetime.now(tz).date()
        start_day = end_day - timedelta(days=max(days - 1, 1))
        generated_at = datetime.now(tz)
        period_hours = max(days * 24, 1)

        devices = list(db.execute(select(Device).where(Device.active.is_(True))).scalars().all())
        rows: list[DeviceUptimeRow] = []

        for device in devices:
            online_hours = 0.0
            if device.last_seen is not None:
                seen = device.last_seen.astimezone(tz)
                window_start = datetime.combine(start_day, datetime.min.time(), tzinfo=tz)
                if seen >= window_start:
                    online_hours = min((generated_at - max(seen - timedelta(hours=period_hours), window_start)).total_seconds() / 3600.0, period_hours)

            if device.health_status == "ONLINE":
                online_hours = float(period_hours)
            elif device.health_status in {"OFFLINE", "DEGRADED"}:
                online_hours = min(online_hours, period_hours * 0.25)

            uptime_percent = round((online_hours / period_hours) * 100.0, 2)
            rows.append(
                DeviceUptimeRow(
                    device_uuid=device.device_uuid,
                    device_name=device.name,
                    uptime_percent=uptime_percent,
                    last_seen=device.last_seen,
                    health_status=device.health_status,
                )
            )

        rows.sort(key=lambda item: item.uptime_percent)
        return DeviceUptimeResponse(
            period_start=start_day,
            period_end=end_day,
            generated_at=generated_at,
            devices=rows,
        )
