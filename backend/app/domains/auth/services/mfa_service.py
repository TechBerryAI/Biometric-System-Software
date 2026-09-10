"""TOTP MFA enrollment and verification."""

from __future__ import annotations

import logging
import secrets

import pyotp
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.redis_keys import with_namespace
from app.core.operator_access import is_env_operator_user
from app.domains.auth.models.user import User

logger = logging.getLogger(__name__)

MFA_ISSUER = "Biometric Attendance"
MFA_CHALLENGE_TTL_SECONDS = 300


class MfaChallengeStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis: Redis | None = None
        try:
            self._redis = Redis.from_url(
                str(self._settings.redis_url),
                socket_timeout=1,
                socket_connect_timeout=1,
                decode_responses=True,
            )
        except Exception:  # noqa: BLE001
            self._redis = None

    def _key(self, challenge_token: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"auth:mfa:challenge:{challenge_token}")

    def create_challenge(self, user_id: int) -> str | None:
        if self._redis is None:
            return None
        token = secrets.token_urlsafe(32)
        try:
            self._redis.setex(self._key(token), MFA_CHALLENGE_TTL_SECONDS, str(user_id))
        except (RedisError, OSError, TimeoutError):
            return None
        return token

    def resolve_user_id(self, challenge_token: str) -> int | None:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(self._key(challenge_token))
        except (RedisError, OSError, TimeoutError):
            return None
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def consume_challenge(self, challenge_token: str) -> int | None:
        user_id = self.resolve_user_id(challenge_token)
        if user_id is None or self._redis is None:
            return user_id
        try:
            self._redis.delete(self._key(challenge_token))
        except (RedisError, OSError, TimeoutError):
            return user_id
        return user_id


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, email: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=MFA_ISSUER)


def enroll_mfa(db: Session, user: User) -> tuple[str, str]:
    """Return (secret, provisioning_uri). MFA stays disabled until verified."""
    secret = generate_mfa_secret()
    user.mfa_secret_encrypted = encrypt_value(secret)
    user.mfa_enabled = False
    db.flush()
    return secret, get_provisioning_uri(secret, user.email)


def confirm_mfa_enrollment(db: Session, user: User, code: str) -> bool:
    if not user.mfa_secret_encrypted:
        return False
    try:
        secret = decrypt_value(user.mfa_secret_encrypted)
    except ValueError:
        logger.warning("MFA enrollment confirm failed: cannot decrypt secret for user_id=%s", user.id)
        return False
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        return False
    user.mfa_enabled = True
    return True


def verify_mfa_code(user: User, code: str) -> bool:
    if not user.mfa_enabled or not user.mfa_secret_encrypted:
        return False
    try:
        secret = decrypt_value(user.mfa_secret_encrypted)
    except ValueError:
        logger.warning("MFA verify failed: cannot decrypt secret for user_id=%s", user.id)
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def disable_mfa(db: Session, user: User) -> None:
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None


def user_requires_mfa(user: User) -> bool:
    if is_env_operator_user(user):
        return False
    settings = get_settings()
    return settings.mfa_required or user.mfa_enabled
