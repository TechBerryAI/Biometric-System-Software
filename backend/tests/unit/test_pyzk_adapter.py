"""Unit tests for PyZK adapter construction."""

from __future__ import annotations

import pytest

from app.core.config import get_settings


@pytest.mark.testid("BE-UNIT-ADAPT-001")
def test_pyzk_adapter_constructs_or_documents_import() -> None:
    try:
        from app.domains.devices.services.pyzk_adapter import PyZKAdapter
    except ImportError as exc:
        pytest.skip(f"pyzk / zk import unavailable: {exc}")

    adapter = PyZKAdapter(get_settings())
    assert adapter is not None
    assert hasattr(adapter, "run")
    assert callable(adapter.run)
