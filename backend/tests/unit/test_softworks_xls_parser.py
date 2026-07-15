"""Unit tests for Softworks four-punch XLS helpers (no live workbook required)."""

from __future__ import annotations

from datetime import time
from pathlib import Path

from app.domains.attendance.services.softworks_xls_parser import (
    month_from_filename,
    parse_hhmm,
)


def test_parse_hhmm_string() -> None:
    assert parse_hhmm("09:58") == time(9, 58)
    assert parse_hhmm("19:12:00") == time(19, 12)
    assert parse_hhmm("") is None
    assert parse_hhmm(None) is None


def test_parse_hhmm_excel_fraction() -> None:
    # 15:30 = 15.5/24
    assert parse_hhmm(15.5 / 24) == time(15, 30)


def test_month_from_filename() -> None:
    assert month_from_filename(Path("March 2026.xls")) == (2026, 3)
    assert month_from_filename(Path("Nov 2025.xls")) == (2025, 11)
    assert month_from_filename(Path("unknown.xls")) is None
