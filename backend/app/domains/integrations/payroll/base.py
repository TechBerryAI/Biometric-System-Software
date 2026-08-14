"""Payroll export adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PayrollExportAdapter(ABC):
    @abstractmethod
    def export(self, rows: list[dict[str, str | int | float | None]]) -> bytes:
        """Serialize payroll rows to target format."""
