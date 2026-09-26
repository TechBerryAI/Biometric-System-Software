"""VM log lines must not say attendance was adjusted."""

from __future__ import annotations

import logging

import pytest

from app.core.logging_config import install_log_redaction


@pytest.mark.testid("BE-UNIT-LOG-001")
def test_formatter_redacts_adjustment_wording() -> None:
    install_log_redaction()
    formatter = logging.Formatter("%(name)s %(message)s")
    leaked = formatter.format(
        logging.LogRecord(
            name="app.domains.attendance.services.attendance_correction_service",
            level=logging.INFO,
            pathname="attendance_correction_service.py",
            lineno=1,
            msg="Inline CORRECT_ATTENDANCE processing failed in correct_attendance",
            args=(),
            exc_info=None,
        )
    )
    assert "CORRECT_ATTENDANCE" not in leaked
    assert "attendance_correction" not in leaked
    assert "correct_attendance" not in leaked
    assert "device_operation" in leaked

    kept = formatter.format(
        logging.LogRecord(
            name="app.workers.tasks",
            level=logging.INFO,
            pathname="tasks.py",
            lineno=1,
            msg="Fleet attendance sync completed POST /attendance/adjust/correct",
            args=(),
            exc_info=None,
        )
    )
    assert "Fleet attendance sync completed" in kept
    assert "/attendance/adjust/correct" in kept
