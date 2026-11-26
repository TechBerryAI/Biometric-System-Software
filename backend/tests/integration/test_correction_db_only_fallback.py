"""Integration: Tier C / unsupported firmware → DB-only correction fallback."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.domains.attendance.services.attendance_correction_service import (
    CORRECTION_STATUS_APPLIED,
    apply_attendance_correction,
)
from tests.factories import make_attendance_log, make_employee, make_operator

UTC = ZoneInfo("UTC")


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CORR-002")
def test_correction_db_only_tier_c_fallback(db_session: Session) -> None:
    operator = make_operator(email="corr-op@example.com")
    emp = make_employee(device_user_id="TBICOR2", name="Tier C Target")
    db_session.add_all([operator, emp])
    db_session.flush()

    day = date(2026, 7, 14)
    old_in = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)
    old_out = datetime(2026, 7, 14, 18, 0, tzinfo=UTC)
    new_in = datetime(2026, 7, 14, 9, 45, tzinfo=UTC)
    new_out = datetime(2026, 7, 14, 17, 15, tzinfo=UTC)
    db_session.add(make_attendance_log(employee=emp, punched_at=old_in, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp, punched_at=old_out, punch_type="1"))
    db_session.commit()
    db_session.refresh(emp)
    db_session.refresh(operator)

    tier_c_caps = {
        "tier": "C",
        "record_size": 0,
        "supports_selective_delete": False,
        "supports_full_rewrite": False,
        "supports_write": False,
    }

    from contextlib import contextmanager

    @contextmanager
    def _noop_lock(*_a, **_k):
        yield

    with (
        patch(
            "app.domains.attendance.services.attendance_correction_service.device_session_lock",
            _noop_lock,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service._probe_device_caps",
            return_value=tier_c_caps,
        ),
        patch("app.domains.attendance.services.attendance_correction_service._CAPS_PROBE_CACHE", {}),
        patch(
            "app.domains.attendance.services.attendance_correction_service.employee_day_lock",
            _noop_lock,
        ),
    ):
        result = apply_attendance_correction(
            db_session,
            employee_id=emp.id,
            local_date=day,
            new_check_in=new_in,
            new_check_out=new_out,
            actor_user_uuid=operator.user_uuid,
            correlation_id="corr-tier-c",
            device_service=MagicMock(),
        )

    assert result.status == CORRECTION_STATUS_APPLIED
    assert result.device_updated is False
    assert result.device_tier == "C"
    assert result.device_command_uuid is not None


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CORR-002")
def test_correction_db_only_mark_absent(db_session: Session) -> None:
    from sqlalchemy import select

    from app.domains.attendance.models.attendance_log import AttendanceLog

    operator = make_operator(email="corr-absent@example.com")
    emp = make_employee(device_user_id="TBICABS", name="Absent Target")
    db_session.add_all([operator, emp])
    db_session.flush()

    day = date(2026, 7, 15)
    old_in = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    old_out = datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
    db_session.add(make_attendance_log(employee=emp, punched_at=old_in, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp, punched_at=old_out, punch_type="1"))
    db_session.commit()
    db_session.refresh(emp)
    db_session.refresh(operator)

    tier_c_caps = {
        "tier": "C",
        "record_size": 0,
        "supports_selective_delete": False,
        "supports_full_rewrite": False,
        "supports_write": False,
    }

    from contextlib import contextmanager

    @contextmanager
    def _noop_lock(*_a, **_k):
        yield

    with (
        patch(
            "app.domains.attendance.services.attendance_correction_service.device_session_lock",
            _noop_lock,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service._probe_device_caps",
            return_value=tier_c_caps,
        ),
        patch("app.domains.attendance.services.attendance_correction_service._CAPS_PROBE_CACHE", {}),
        patch(
            "app.domains.attendance.services.attendance_correction_service.employee_day_lock",
            _noop_lock,
        ),
    ):
        result = apply_attendance_correction(
            db_session,
            employee_id=emp.id,
            local_date=day,
            new_check_in=None,
            new_check_out=None,
            actor_user_uuid=operator.user_uuid,
            correlation_id="corr-absent",
            device_service=MagicMock(),
        )

    assert result.status == CORRECTION_STATUS_APPLIED
    assert result.new_check_in is None
    assert result.new_check_out is None
    remaining = db_session.execute(
        select(AttendanceLog).where(AttendanceLog.employee_code == emp.device_user_id)
    ).scalars().all()
    assert remaining == []
