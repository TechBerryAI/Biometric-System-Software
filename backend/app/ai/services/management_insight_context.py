"""Aggregate attendance context for management narratives (no individual names sent to models)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.employees.models.employee import Employee
from app.domains.attendance.schemas import DailySummaryRow
from app.domains.attendance.services.daily_summary_service import compute_daily_summaries_range


def _trailing_dates(settings: Settings, count: int) -> list[date]:
    tz = ZoneInfo(settings.resolved_timezone())
    today = datetime.now(tz).date()
    return [today - timedelta(days=count - 1 - i) for i in range(count)]


def _department_rollup_today(
    summary_rows: list[DailySummaryRow],
    employees: list[Employee],
) -> list[dict[str, float | int | str | None]]:
    by_id = {e.id: e for e in employees}

    def dept_of(employee_id: int) -> str:
        e = by_id.get(employee_id)
        return (e.department or "").strip() or "Unassigned"

    reg: dict[str, int] = {}
    for e in employees:
        d = (e.department or "").strip() or "Unassigned"
        reg[d] = reg.get(d, 0) + 1

    stats: dict[str, dict[str, int | float]] = {}
    for r in summary_rows:
        d = dept_of(r.employee_id)
        if d not in stats:
            stats[d] = {"present": 0, "work_sum": 0, "work_n": 0}
        s = stats[d]
        if r.first_check_in is not None:
            s["present"] += 1  # type: ignore[operator]
            if r.total_work_minutes is not None:
                s["work_sum"] += r.total_work_minutes  # type: ignore[operator]
                s["work_n"] += 1  # type: ignore[operator]

    depts = sorted(set(reg.keys()) | set(stats.keys()))
    out: list[dict[str, float | int | str | None]] = []
    for department in depts:
        s = stats.get(department, {"present": 0, "work_sum": 0, "work_n": 0})
        work_n = int(s["work_n"])
        out.append(
            {
                "department": department,
                "registered": reg.get(department, 0),
                "present": int(s["present"]),
                "avg_work_minutes": float(s["work_sum"]) / work_n if work_n > 0 else None,
            }
        )
    return out


def build_management_insight_context(db: Session, settings: Settings, trend_days: int = 14) -> dict:
    """Structured aggregates only — safe to send to an external LLM."""
    dates = _trailing_dates(settings, trend_days)
    summaries_by_day = compute_daily_summaries_range(db, dates[0], dates[-1], settings)
    trend: list[dict[str, float | int | str | None]] = []
    today_rows: list[DailySummaryRow] | None = None

    for d in dates:
        rows = summaries_by_day.get(d, [])
        if d == dates[-1]:
            today_rows = rows
        headcount = len(rows)
        present = sum(1 for r in rows if r.first_check_in is not None)
        absent = headcount - present
        with_span = [r for r in rows if r.first_check_in is not None and r.total_work_minutes is not None]
        sum_work = sum(r.total_work_minutes or 0 for r in with_span)
        avg_work = sum_work / len(with_span) if with_span else None
        trend.append(
            {
                "date": d.isoformat(),
                "present": present,
                "absent": absent,
                "headcount": headcount,
                "attendance_rate_percent": (present / headcount * 100) if headcount else 0.0,
                "avg_work_minutes": avg_work,
                "sum_work_minutes": sum_work,
            }
        )

    employees = list(
        db.execute(select(Employee).where(Employee.departed_at.is_(None)).order_by(Employee.id)).scalars().all()
    )
    if today_rows is None:
        today_rows = summaries_by_day.get(dates[-1], [])

    return {
        "timezone": settings.resolved_timezone(),
        "roster_size": len(employees),
        "trend_days": trend_days,
        "daily_trend": trend,
        "department_today": _department_rollup_today(today_rows, employees),
    }
