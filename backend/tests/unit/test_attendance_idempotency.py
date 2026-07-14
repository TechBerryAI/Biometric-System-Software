"""Unit tests for attendance insert idempotency helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.domains.attendance.services.attendance_service import prune_recent_duplicate_logs


class FakeSession:
    """Minimal stand-in; prune_recent_duplicate_logs ignores the session."""


@pytest.mark.testid("BE-UNIT-IDEM-001")
def test_prune_recent_duplicate_logs_is_noop() -> None:
    """History retention policy: prune never deletes and always returns 0."""
    settings = get_settings()
    deleted = prune_recent_duplicate_logs(FakeSession(), settings=settings, days=7)  # type: ignore[arg-type]
    assert deleted == 0

    deleted_again = prune_recent_duplicate_logs(SimpleNamespace(), settings=settings)  # type: ignore[arg-type]
    assert deleted_again == 0
