"""Env-backed GOD-mode operator principal, capabilities, and session refresh storage."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace
from app.domains.auth.models.user import User
from app.domains.auth.schemas import UserCapabilities

ACCOUNT_FLAG_EXTENDED = 1


class SessionStoreUnavailable(RuntimeError):
    """Raised when the operator refresh-token store cannot persist a session."""


class _OperatorUser(Protocol):
    role: str | None
    account_flags: int


@dataclass(frozen=True, slots=True)
class EnvOperatorUser:
    """Synthetic session principal for the env-backed operator account."""

    user_uuid: str
    email: str
    role: str = "SUPER_ADMIN"
    account_flags: int = ACCOUNT_FLAG_EXTENDED
    active: bool = True
    full_name: str | None = None
    mfa_enabled: bool = False
    id: None = None


AuthPrincipal = User | EnvOperatorUser


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


class OperatorRefreshTokenStore:
    """Redis-backed refresh tokens for the env operator (no users.id FK)."""

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

    def _key(self, token_hash: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"auth:operator:refresh:{token_hash}")

    def _ttl_seconds(self) -> int:
        return self._settings.refresh_token_expire_days * 86400

    def store(self, *, token_hash: str, family_id: str, expires_at: datetime) -> bool:
        if self._redis is None:
            return False
        payload = json.dumps(
            {
                "family_id": family_id,
                "expires_at": _as_utc(expires_at).isoformat(),
                "revoked": False,
            }
        )
        key = self._key(token_hash)
        ttl = self._ttl_seconds()
        for attempt in range(2):
            try:
                self._redis.setex(key, ttl, payload)
                return True
            except (RedisError, OSError, TimeoutError):
                if attempt == 0:
                    continue
                return False
        return False

    def load(self, token_hash: str) -> dict[str, str | bool] | None:
        if self._redis is None:
            return None
        raw = None
        for attempt in range(2):
            try:
                raw = self._redis.get(self._key(token_hash))
                break
            except (RedisError, OSError, TimeoutError):
                if attempt == 0:
                    continue
                return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def delete(self, token_hash: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._key(token_hash))
        except (RedisError, OSError, TimeoutError):
            return

    def revoke_family(self, family_id: str) -> None:
        if self._redis is None:
            return
        pattern = with_namespace(self._settings.redis_namespace, "auth:operator:refresh:*")
        try:
            for key in self._redis.scan_iter(match=pattern, count=100):
                raw = self._redis.get(key)
                if raw is None:
                    continue
                try:
                    data = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict) and data.get("family_id") == family_id:
                    self._redis.delete(key)
        except (RedisError, OSError, TimeoutError):
            return


def is_env_operator_user(user: AuthPrincipal | None) -> bool:
    return isinstance(user, EnvOperatorUser)


def is_env_operator_configured() -> bool:
    settings = get_settings()
    return bool(settings.auth_operator_email and settings.auth_operator_password)


def normalized_operator_email() -> str | None:
    settings = get_settings()
    if not settings.auth_operator_email:
        return None
    return settings.auth_operator_email.strip().lower()


def is_env_operator_email(email: str) -> bool:
    operator_email = normalized_operator_email()
    if operator_email is None:
        return False
    return secrets.compare_digest(email.strip().lower(), operator_email)


def is_env_operator_uuid(user_uuid: str | None) -> bool:
    if not user_uuid or not is_env_operator_configured():
        return False
    settings = get_settings()
    return secrets.compare_digest(user_uuid.strip(), settings.auth_operator_uuid.strip())


def build_env_operator() -> EnvOperatorUser | None:
    if not is_env_operator_configured():
        return None
    settings = get_settings()
    return EnvOperatorUser(
        user_uuid=settings.auth_operator_uuid.strip(),
        email=normalized_operator_email() or "",
    )


def authenticate_env_operator(email: str, password: str) -> EnvOperatorUser | None:
    if not is_env_operator_configured():
        return None
    if not is_env_operator_email(email):
        return None
    settings = get_settings()
    expected_password = settings.auth_operator_password or ""
    if not secrets.compare_digest(password, expected_password):
        return None
    return build_env_operator()


def is_operator_account(user: _OperatorUser | None) -> bool:
    if user is None:
        return False
    if is_env_operator_user(user):
        return True
    flags = int(getattr(user, "account_flags", 0) or 0)
    return user.role == "SUPER_ADMIN" and (flags & ACCOUNT_FLAG_EXTENDED) != 0


def is_operator_user_uuid(db: Session, user_uuid: str | None) -> bool:
    if not user_uuid:
        return False
    if is_env_operator_uuid(user_uuid):
        return is_env_operator_configured()
    user = db.execute(select(User).where(User.user_uuid == user_uuid.strip())).scalar_one_or_none()
    return is_operator_account(user)


def resolve_user_by_uuid(db: Session, user_uuid: str | None) -> AuthPrincipal | None:
    if not user_uuid:
        return None
    if is_env_operator_uuid(user_uuid):
        return build_env_operator()
    return db.execute(select(User).where(User.user_uuid == user_uuid.strip())).scalar_one_or_none()


def user_capabilities(user: _OperatorUser | None) -> UserCapabilities:
    operator = is_operator_account(user)
    return UserCapabilities(
        attendance_adjust=operator,
        forensic_audit=operator,
    )


def store_operator_refresh_token(*, token_hash: str, family_id: str, expires_at: datetime) -> bool:
    return OperatorRefreshTokenStore().store(
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
    )


def revoke_operator_refresh_token(raw_refresh_token: str) -> bool:
    from app.core.security import hash_refresh_token

    token_hash = hash_refresh_token(raw_refresh_token)
    store = OperatorRefreshTokenStore()
    record = store.load(token_hash)
    if record is None:
        return False
    family_id = record.get("family_id")
    if isinstance(family_id, str):
        store.revoke_family(family_id)
    else:
        store.delete(token_hash)
    return True


def rotate_operator_refresh_token(
    raw_refresh_token: str,
    issue_tokens: Callable[[EnvOperatorUser, str], tuple[str, str, datetime]],
) -> tuple[EnvOperatorUser, str, str, datetime] | None:
    from app.core.security import hash_refresh_token

    operator = build_env_operator()
    if operator is None:
        return None

    token_hash = hash_refresh_token(raw_refresh_token)
    store = OperatorRefreshTokenStore()
    record = store.load(token_hash)
    if record is None:
        return None
    if record.get("revoked"):
        family_id = record.get("family_id")
        if isinstance(family_id, str):
            store.revoke_family(family_id)
        return None

    expires_raw = record.get("expires_at")
    if not isinstance(expires_raw, str):
        return None
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except ValueError:
        return None
    if _as_utc(expires_at) <= _as_utc(_utcnow()):
        store.delete(token_hash)
        return None

    family_id = record.get("family_id")
    if not isinstance(family_id, str):
        return None

    store.delete(token_hash)
    access_token, new_refresh, refresh_expiry = issue_tokens(operator, family_id)
    return operator, access_token, new_refresh, refresh_expiry


def operator_refresh_expiry() -> datetime:
    settings = get_settings()
    return _utcnow() + timedelta(days=settings.refresh_token_expire_days)
