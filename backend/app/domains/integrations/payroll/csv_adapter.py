"""CSV payroll export adapter."""

from __future__ import annotations

import csv
import io

from app.domains.integrations.payroll.base import PayrollExportAdapter


class CsvPayrollExportAdapter(PayrollExportAdapter):
    def export(self, rows: list[dict[str, str | int | float | None]]) -> bytes:
        buffer = io.StringIO()
        if not rows:
            writer = csv.writer(buffer)
            writer.writerow(["employee_code", "employee_name", "work_date", "work_minutes", "status"])
            return buffer.getvalue().encode("utf-8")

        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8")
