"""Fernet envelope encryption for secrets at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings


def _derive_fernet_key(raw_key: str) -> bytes:
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet(settings: Settings | None = None) -> Fernet:
    settings = settings or get_settings()
    raw = settings.encryption_key
    if not raw:
        raise ValueError("ENCRYPTION_KEY is not configured")
    return Fernet(_derive_fernet_key(raw))


def encrypt_value(plaintext: str, settings: Settings | None = None) -> str:
    fernet = get_fernet(settings)
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, settings: Settings | None = None) -> str:
    fernet = get_fernet(settings)
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted payload") from exc
