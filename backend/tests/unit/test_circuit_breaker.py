"""Unit tests for circuit breaker."""

from __future__ import annotations

import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError


@pytest.mark.testid("BE-UNIT-CB-001")
def test_circuit_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=60, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")), retry_attempts=1)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")), retry_attempts=1)
    assert breaker.can_execute() is False
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: 1)


@pytest.mark.testid("BE-UNIT-CB-002")
def test_circuit_success_resets() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=60, name="t")
    assert breaker.call(lambda: 42) == 42
    assert breaker.can_execute() is True
