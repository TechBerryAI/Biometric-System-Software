"""Unit tests for Fernet envelope encryption."""

from __future__ import annotations

import pytest

from app.core.crypto import decrypt_value, encrypt_value, get_fernet


@pytest.mark.testid("BE-UNIT-CRYPTO-001")
def test_encrypt_decrypt_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-encryption-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    plaintext = "super-secret-mfa-key"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


@pytest.mark.testid("BE-UNIT-CRYPTO-002")
def test_get_fernet_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        get_fernet()


@pytest.mark.testid("BE-UNIT-CRYPTO-003")
def test_decrypt_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-encryption-key")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Invalid encrypted payload"):
        decrypt_value("not-valid-ciphertext")
