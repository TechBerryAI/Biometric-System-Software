"""Unit tests for CSV payroll export adapter."""

from __future__ import annotations

import csv
import io

import pytest

from app.domains.integrations.payroll.csv_adapter import CsvPayrollExportAdapter


@pytest.mark.testid("BE-UNIT-PAYROLL-001")
def test_csv_payroll_export_adapter_writes_header_for_empty_rows() -> None:
    adapter = CsvPayrollExportAdapter()
    payload = adapter.export([])
    text = payload.decode("utf-8")
    assert "employee_code" in text


@pytest.mark.testid("BE-UNIT-PAYROLL-002")
def test_csv_payroll_export_adapter_serializes_rows() -> None:
    adapter = CsvPayrollExportAdapter()
    payload = adapter.export(
        [
            {
                "employee_code": "E001",
                "employee_name": "Alice",
                "work_date": "2026-07-01",
                "work_minutes": 480,
                "status": "complete",
            }
        ]
    )
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8"))))
    assert rows[0]["employee_code"] == "E001"
    assert rows[0]["work_minutes"] == "480"
