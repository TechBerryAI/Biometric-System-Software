"""Integration: punch storage completeness (full day, floor, push buffer)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_service import (
    _dedupe_device_records,
    _incremental_sync_floor,
    insert_attendance_logs_idempotent,
    run_device_sync,
)
from app.domains.devices.gateway.device_auth import (
    build_signature_payload,
    generate_device_secret,
    hash_device_secret,
    sign_request,
)
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from app.domains.devices.services.sync_manager_service import sync_device
from tests.factories import make_attendance_log, make_device, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-001")
def test_full_day_punch_sequence_all_stored(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIFULL1")
    db_session.add(emp)
    db_session.commit()

    day = datetime(2026, 7, 14, tzinfo=UTC)
    # status: 0=in, 2=break-out, 3=break-in, 2=lunch-out, 3=lunch-in, 1=out, late out next day
    sequence = [
        (day.replace(hour=9, minute=0), 0),
        (day.replace(hour=11, minute=0), 2),
        (day.replace(hour=11, minute=15), 3),
        (day.replace(hour=13, minute=0), 2),
        (day.replace(hour=13, minute=45), 3),
        (day.replace(hour=18, minute=30), 1),
        (day.replace(hour=23, minute=50), 1),
        (day.replace(day=15, hour=0, minute=20), 1),
    ]
    records = [
        DeviceAttendanceRecord(user_id="TBIFULL1", timestamp=ts, punch=0, status=status)
        for ts, status in sequence
    ]
    inserted = insert_attendance_logs_idempotent(db_session, records, "main-entrance")
    assert inserted == len(sequence)
    count = db_session.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
    assert count == len(sequence)


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-002")
def test_incremental_floor_no_global_fallback(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIFLOOR1")
    db_session.add(emp)
    db_session.add(
        make_attendance_log(
            employee=emp,
            punched_at=datetime(2026, 7, 20, 18, 0, tzinfo=UTC),
            device_id="other-gate",
        )
    )
    db_session.commit()

    settings = get_settings()
    floor = _incremental_sync_floor(db_session, device_id="new-gate", settings=settings)
    assert floor is None


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-003")
def test_incremental_floor_uses_device_latest(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIFLOOR2")
    latest = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    db_session.add(emp)
    db_session.add(make_attendance_log(employee=emp, punched_at=latest, device_id="gate-x"))
    db_session.commit()

    settings = get_settings()
    floor = _incremental_sync_floor(db_session, device_id="gate-x", settings=settings)
    assert floor is not None
    floor_aware = floor if floor.tzinfo is not None else floor.replace(tzinfo=UTC)
    assert floor_aware == latest - timedelta(minutes=settings.device_sync_overlap_minutes)


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-004")
def test_exact_batch_dedupe_only(db_session: Session) -> None:
    del db_session
    ts = datetime(2026, 7, 14, 9, 0, 0, tzinfo=UTC)
    near = ts + timedelta(seconds=5)
    records = [
        DeviceAttendanceRecord(user_id="U1", timestamp=ts, punch=0, status=0),
        DeviceAttendanceRecord(user_id="U1", timestamp=ts, punch=0, status=0),  # exact dup
        DeviceAttendanceRecord(user_id="U1", timestamp=near, punch=0, status=0),  # kept
    ]
    out = _dedupe_device_records(records)
    assert len(out) == 2
    assert out[0].timestamp == ts
    assert out[1].timestamp == near


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-005")
def test_push_buffer_ingested_then_cleared(db_session: Session, client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Push attendance is written to DB and buffer cleared only after successful sync."""
    from app.domains.devices.gateway.router import reset_device_gateway

    reset_device_gateway()
    secret = generate_device_secret()
    device = make_device(name="push-gate", connectivity_mode="push", ip_address="10.0.0.9")
    device.device_secret_hash = hash_device_secret(secret)
    emp = make_employee(device_user_id="TBIPUSH1")
    db_session.add(device)
    db_session.add(emp)
    db_session.commit()

    ts = datetime(2026, 7, 14, 10, 0, 0, tzinfo=UTC).isoformat()
    body_obj = {
        "attendance": [{"user_id": "TBIPUSH1", "timestamp": ts, "punch": 0, "status": 0}],
        "trigger_sync": True,
    }
    raw = json.dumps(body_obj).encode()
    stamp = str(int(time.time()))
    nonce = "push-nonce-1"
    payload = build_signature_payload(
        device_id="push-gate",
        timestamp=stamp,
        nonce=nonce,
        body=raw,
    )
    sig = sign_request(secret, payload)

    with (
        patch(
            "app.domains.devices.services.sync_manager_service.device_session_lock",
        ) as lock_mock,
        patch(
            "app.domains.devices.services.sync_manager_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service.load_corrected_day_guards",
            return_value={},
        ),
        patch(
            "app.domains.devices.gateway.device_auth.DeviceAuthService.is_replay",
            return_value=False,
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        from contextlib import contextmanager

        @contextmanager
        def _noop_lock(*_a, **_k):
            yield

        lock_mock.side_effect = _noop_lock
        response = client.post(
            "/devices/gateway/push/push-gate",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Device-Timestamp": stamp,
                "X-Device-Nonce": nonce,
                "X-Device-Signature": sig,
                "X-Device-Secret": secret,
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["sync"] is not None
    assert body["sync"].get("inserted", 0) >= 1

    logs = db_session.execute(select(AttendanceLog)).scalars().all()
    assert len(logs) >= 1
    assert logs[0].employee_code == "TBIPUSH1"
    assert logs[0].device_id == "push-gate"

    db_session.refresh(device)
    assert device.offline_buffer in (None, {})


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-007")
def test_push_buffer_retained_when_punches_missing_after_insert(
    db_session: Session, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not clear offline_buffer when reconcile reports missing punches."""
    from app.domains.devices.gateway.router import reset_device_gateway

    reset_device_gateway()
    secret = generate_device_secret()
    device = make_device(name="push-retain", connectivity_mode="push", ip_address="10.0.0.11")
    device.device_secret_hash = hash_device_secret(secret)
    emp = make_employee(device_user_id="TBIPUSH2")
    db_session.add(device)
    db_session.add(emp)
    db_session.commit()

    ts = datetime(2026, 7, 14, 11, 0, 0, tzinfo=UTC).isoformat()
    body_obj = {
        "attendance": [{"user_id": "TBIPUSH2", "timestamp": ts, "punch": 0, "status": 0}],
        "trigger_sync": True,
    }
    raw = json.dumps(body_obj).encode()
    stamp = str(int(time.time()))
    nonce = "push-nonce-retain"
    payload = build_signature_payload(
        device_id="push-retain",
        timestamp=stamp,
        nonce=nonce,
        body=raw,
    )
    sig = sign_request(secret, payload)

    with (
        patch(
            "app.domains.devices.services.sync_manager_service.device_session_lock",
        ) as lock_mock,
        patch(
            "app.domains.devices.services.sync_manager_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.devices.services.sync_manager_service.run_user_sync",
            return_value=(1, 0),
        ),
        patch(
            "app.domains.devices.services.sync_manager_service.run_device_sync_detailed",
            return_value=MagicMock(
                fetched=1,
                inserted=0,
                placeholders=0,
                skipped_corrected_punches=0,
                punches_missing_after_insert=1,
                skipped_reason=None,
            ),
        ),
        patch(
            "app.domains.devices.gateway.device_auth.DeviceAuthService.is_replay",
            return_value=False,
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        from contextlib import contextmanager

        @contextmanager
        def _noop_lock(*_a, **_k):
            yield

        lock_mock.side_effect = _noop_lock
        response = client.post(
            "/devices/gateway/push/push-retain",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Device-Timestamp": stamp,
                "X-Device-Nonce": nonce,
                "X-Device-Signature": sig,
                "X-Device-Secret": secret,
            },
        )

    assert response.status_code == 200, response.text
    db_session.refresh(device)
    assert device.offline_buffer is not None
    assert len(device.offline_buffer.get("attendance") or []) >= 1


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-006")
def test_push_sync_failure_retains_buffer(db_session: Session) -> None:
    device = make_device(name="push-fail", connectivity_mode="push")
    device.offline_buffer = {
        "attendance": [
            {
                "user_id": "X1",
                "timestamp": datetime(2026, 7, 14, 9, 0, tzinfo=UTC).isoformat(),
                "punch": 0,
                "status": 0,
            }
        ]
    }
    db_session.add(device)
    db_session.commit()

    with (
        patch(
            "app.domains.devices.services.sync_manager_service.device_session_lock",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.domains.devices.services.sync_manager_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
    ):
        with pytest.raises(RuntimeError):
            sync_device(db_session, device, full_resync=False)

    db_session.refresh(device)
    assert device.offline_buffer is not None
    assert len(device.offline_buffer.get("attendance") or []) == 1


@pytest.mark.integration
@pytest.mark.testid("BE-INT-PUNCH-008")
def test_run_device_sync_stamps_real_device_id(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBISTAMP1")
    db_session.add(emp)
    db_session.commit()

    ts = datetime(2026, 7, 14, 9, 0, 0, tzinfo=UTC)
    device = MagicMock()
    device.fetch_attendance.return_value = [
        DeviceAttendanceRecord(user_id="TBISTAMP1", timestamp=ts, punch=0, status=0)
    ]

    with (
        patch(
            "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service.load_corrected_day_guards",
            return_value={},
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        _, inserted, _ = run_device_sync(
            db_session, device=device, full_resync=True, device_id="branch-lobby"
        )

    assert inserted == 1
    log = db_session.execute(select(AttendanceLog)).scalar_one()
    assert log.device_id == "branch-lobby"
