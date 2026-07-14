"""Unit tests for attlog capability probing."""

from __future__ import annotations

import pytest

from app.domains.devices.services.device_attlog_protocol import probe_attlog_capabilities
from tests.mocks.pyzk_simulator import SimulatedPyZKDevice


@pytest.mark.testid("BE-UNIT-PROTO-001")
def test_probe_attlog_capabilities_tier_a_on_simulator() -> None:
    device = SimulatedPyZKDevice()
    device.set_user(user_id="TBI001", name="Unmesh Tari", uid=1)
    conn = device.connection()

    caps = probe_attlog_capabilities(conn, allow_tier_b_write=False)

    assert caps.tier == "A"
    assert caps.record_size == 40
    assert caps.supports_selective_delete is True
    assert caps.supports_full_rewrite is True
    assert caps.supports_write is True
