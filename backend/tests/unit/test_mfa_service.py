"""Unit tests for MFA verification hardening."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.domains.auth.services.mfa_service import confirm_mfa_enrollment, verify_mfa_code


@pytest.mark.testid("BE-UNIT-MFA-001")
def test_verify_mfa_code_decrypt_failure_returns_false() -> None:
    user = SimpleNamespace(id=1, mfa_enabled=True, mfa_secret_encrypted="bad-ciphertext")
    with patch(
        "app.domains.auth.services.mfa_service.decrypt_value",
        side_effect=ValueError("Invalid encrypted payload"),
    ):
        assert verify_mfa_code(user, "123456") is False


@pytest.mark.testid("BE-UNIT-MFA-002")
def test_confirm_mfa_enrollment_decrypt_failure_returns_false() -> None:
    user = SimpleNamespace(id=1, mfa_secret_encrypted="bad-ciphertext", mfa_enabled=False)
    with patch(
        "app.domains.auth.services.mfa_service.decrypt_value",
        side_effect=ValueError("ENCRYPTION_KEY is not configured"),
    ):
        assert confirm_mfa_enrollment(db=None, user=user, code="123456") is False
    assert user.mfa_enabled is False
