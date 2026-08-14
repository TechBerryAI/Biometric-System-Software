"""Unit tests for Redlock."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.redis_lock import LockHandle, Redlock, reset_redlock


@pytest.mark.testid("BE-UNIT-REDLOCK-001")
def test_redlock_acquire_release_single_node() -> None:
    reset_redlock()
    lock = Redlock.__new__(Redlock)
    fake = MagicMock()
    fake.set.return_value = True
    fake.eval.return_value = 1
    lock._settings = MagicMock(redis_namespace="biometric")
    lock._clients = [fake]
    lock._quorum = 1

    handle = lock.acquire("device:1", ttl_ms=1000)
    assert handle is not None
    assert handle.acquired is True
    lock.release(handle)
    fake.eval.assert_called()
    reset_redlock()


@pytest.mark.testid("BE-UNIT-REDLOCK-002")
def test_redlock_fails_without_clients() -> None:
    reset_redlock()
    lock = Redlock.__new__(Redlock)
    lock._settings = MagicMock(redis_namespace="biometric")
    lock._clients = []
    lock._quorum = 1
    assert lock.acquire("x") is None
    reset_redlock()


@pytest.mark.testid("BE-UNIT-REDLOCK-003")
def test_redlock_context_manager() -> None:
    reset_redlock()
    lock = Redlock.__new__(Redlock)
    fake = MagicMock()
    fake.set.return_value = True
    lock._settings = MagicMock(redis_namespace="biometric")
    lock._clients = [fake]
    lock._quorum = 1
    with lock.lock("job", blocking_timeout=0) as handle:
        assert isinstance(handle, LockHandle)
    reset_redlock()
