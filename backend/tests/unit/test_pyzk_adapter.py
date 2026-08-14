"""Unit tests for PyZK adapter construction."""

from __future__ import annotations

import errno
from unittest.mock import MagicMock, patch

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


@pytest.mark.testid("BE-UNIT-ADAPT-002")
def test_pyzk_adapter_fails_fast_on_no_route() -> None:
    try:
        from app.domains.devices.services.pyzk_adapter import PyZKAdapter
    except ImportError as exc:
        pytest.skip(f"pyzk / zk import unavailable: {exc}")

    adapter = PyZKAdapter(get_settings())
    zk = MagicMock()
    zk.connect.side_effect = OSError(errno.EHOSTUNREACH, "No route to host")

    with patch.object(adapter, "_make_zk", return_value=zk):
        with pytest.raises(RuntimeError, match="after 1 attempts"):
            adapter.run("fetch_users", lambda _c: None, max_attempts=3)

    assert zk.connect.call_count == 1
