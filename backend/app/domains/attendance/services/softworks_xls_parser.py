"""Parse Softworks / eTimeTrack monthly \"Four Punch\" status XLS exports into punch events.

These reports are *not* full transaction logs — at most InTime1/OutTime1/InTime2/OutTime2
per employee per calendar day. Empty months (all Absent / no time cells) yield no punches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd

_EMP_RE = re.compile(r"^(\S+)\s*:\s*(.+)$")
_DAY_RE = re.compile(r"^(\d+)\s")
_TIME_LABELS = ("InTime1", "OutTime1", "InTime2", "OutTime2")

# Softworks monthly report file names → (year, month)
FILENAME_MONTHS: dict[str, tuple[int, int]] = {
    "august 2025.xls": (2025, 8),
    "september 2025.xls": (2025, 9),
    "october 2025.xls": (2025, 10),
    "nov 2025.xls": (2025, 11),
    "november 2025.xls": (2025, 11),
    "december 2025.xls": (2025, 12),
    "january 2026.xls": (2026, 1),
    "feb 2026.xls": (2026, 2),
    "february 2026.xls": (2026, 2),
    "march 2026.xls": (2026, 3),
    "april 2026.xls": (2026, 4),
    "may 2026.xls": (2026, 5),
    "june 2026.xls": (2026, 6),
    "july 2026.xls": (2026, 7),
}


@dataclass(frozen=True, slots=True)
class SoftworksPunch:
    employee_code: str
    employee_name: str
    timestamp: datetime
    direction: str  # "in" | "out"
    source_label: str  # InTime1 / OutTime1 / …


def parse_hhmm(value: object) -> time | None:
    """Parse Softworks cell (HH:MM string or Excel day-fraction) into a local time."""
    if value in ("", None):
        return None
    if isinstance(value, float):
        total_minutes = int(round(value * 24 * 60)) % (24 * 60)
        return time(total_minutes // 60, total_minutes % 60)
    if isinstance(value, int):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def month_from_filename(path: Path) -> tuple[int, int] | None:
    return FILENAME_MONTHS.get(path.name.lower())


def _day_columns(sheet: xlrd.sheet.Sheet) -> dict[int, int]:
    """Map column index → calendar day number from the Days header row."""
    out: dict[int, int] = {}
    header_row = 6
    if sheet.nrows <= header_row:
        return out
    for col in range(sheet.ncols):
        raw = str(sheet.cell_value(header_row, col)).strip()
        match = _DAY_RE.match(raw)
        if match:
            out[col] = int(match.group(1))
    return out


def _employee_on_row(sheet: xlrd.sheet.Sheet, row: int) -> tuple[str, str] | None:
    for col in range(sheet.ncols):
        value = sheet.cell_value(row, col)
        if not isinstance(value, str):
            continue
        match = _EMP_RE.match(value.strip())
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return None


def parse_four_punch_workbook(
    path: Path,
    *,
    year: int,
    month: int,
    timezone: str = "Asia/Kolkata",
) -> list[SoftworksPunch]:
    """Extract punch events from one Softworks monthly four-punch XLS."""
    tz = ZoneInfo(timezone)
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    day_cols = _day_columns(sheet)
    if not day_cols:
        return []

    punches: list[SoftworksPunch] = []
    row = 0
    while row < sheet.nrows:
        if str(sheet.cell_value(row, 0)).strip() != "Employee:":
            row += 1
            continue
        emp = _employee_on_row(sheet, row)
        label_rows: dict[str, int] = {}
        for look in range(row + 1, min(row + 12, sheet.nrows)):
            label = str(sheet.cell_value(look, 0)).strip()
            if label in _TIME_LABELS:
                label_rows[label] = look
        if emp and label_rows:
            code, name = emp
            for label, label_row in label_rows.items():
                direction = "in" if label.startswith("In") else "out"
                for col, day_num in day_cols.items():
                    parsed_time = parse_hhmm(sheet.cell_value(label_row, col))
                    if parsed_time is None:
                        continue
                    try:
                        day = date(year, month, day_num)
                    except ValueError:
                        continue
                    punches.append(
                        SoftworksPunch(
                            employee_code=code,
                            employee_name=name,
                            timestamp=datetime.combine(day, parsed_time, tzinfo=tz),
                            direction=direction,
                            source_label=label,
                        )
                    )
        row += 1
    return punches


def iter_softworks_month_files(directory: Path) -> list[tuple[Path, int, int]]:
    """List (path, year, month) for known Softworks monthly XLS files in directory."""
    found: list[tuple[Path, int, int]] = []
    for path in sorted(directory.glob("*.xls")):
        ym = month_from_filename(path)
        if ym is None:
            continue
        found.append((path, ym[0], ym[1]))
    return found
