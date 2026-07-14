"""Unit tests for ZK attlog codec encode/decode."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domains.devices.services.device_attlog_codec import decode_time_zk, encode_attlog_record_40, encode_time_zk


@pytest.mark.testid("BE-UNIT-CODEC-001")
def test_encode_decode_time_zk_roundtrip() -> None:
    original = datetime(2026, 7, 14, 9, 30, 45)
    encoded = encode_time_zk(original)
    assert isinstance(encoded, bytes)
    assert len(encoded) == 4
    assert decode_time_zk(encoded) == original


@pytest.mark.testid("BE-UNIT-CODEC-001")
def test_encode_attlog_record_40_length() -> None:
    blob = encode_attlog_record_40(
        uid=1,
        user_id="TBI001",
        timestamp=datetime(2026, 7, 14, 10, 0, 0),
        status=0,
        punch=0,
    )
    assert len(blob) == 40
