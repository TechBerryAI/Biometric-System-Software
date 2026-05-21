"""Authentication workflows: login throttling, rotation, and admin bootstrap."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole

ALLOWED_APP_ROLES = {
    UserRole.SUPER_ADMIN.value,
    UserRole.HR_ADMIN.value,
    UserRole.IT_ADMIN.value,
    UserRole.CEO.value,
}


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


class LoginRateLimiter:
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

    def _key(self, email: str) -> str:
        key = f"auth:login:fail:{email.strip().lower()}"
        return with_namespace(self._settings.redis_namespace, key)

    def is_blocked(self, email: str) -> bool:
        if self._redis is None:
            return False
        try:
            raw = self._redis.get(self._key(email))
        except (RedisError, OSError, TimeoutError):
            # Operational fallback: auth continues even if Redis is unavailable.
            return False
        try:
            count = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            count = 0
        return count >= self._settings.login_attempt_max

    def register_failure(self, email: str) -> None:
        if self._redis is None:
            return
        try:
            key = self._key(email)
            count = self._redis.incr(key)
            if count <= 1:
                self._redis.expire(key, self._settings.login_attempt_window_seconds)
        except (RedisError, OSError, TimeoutError):
            return

    def register_success(self, email: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._key(email))
        except (RedisError, OSError, TimeoutError):
            return


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None or not user.active:
        return None
    if user.role not in ALLOWED_APP_ROLES:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_session_tokens(db: Session, user: User) -> tuple[str, str, datetime]:
    settings = get_settings()
    access_token, _ = create_access_token(user_uuid=user.user_uuid, role=user.role, email=user.email)
    refresh_token = generate_refresh_token()
    refresh_expiry = _utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expiry,
            revoked=False,
        )
    )
    user.last_login = _utcnow()
    return access_token, refresh_token, refresh_expiry


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[User, str, str, datetime] | None:
    token_hash = hash_refresh_token(raw_refresh_token)
    refresh = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if refresh is None or refresh.revoked or refresh.expires_at <= _utcnow():
        return None
    user = db.get(User, refresh.user_id)
    if user is None or not user.active:
        return None
    refresh.revoked = True
    access_token, new_refresh, refresh_expiry = issue_session_tokens(db, user)
    return user, access_token, new_refresh, refresh_expiry


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> bool:
    token_hash = hash_refresh_token(raw_refresh_token)
    refresh = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if refresh is None:
        return False
    refresh.revoked = True
    return True


def ensure_bootstrap_admin(db: Session) -> User | None:
    settings = get_settings()
    if not settings.auth_bootstrap_admin_email or not settings.auth_bootstrap_admin_password:
        return None
    normalized_email = settings.auth_bootstrap_admin_email.strip().lower()
    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email=normalized_email,
        password_hash=hash_password(settings.auth_bootstrap_admin_password),
        role=UserRole.SUPER_ADMIN.value,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_or_update_user(
    db: Session,
    *,
    email: str,
    full_name: str | None = None,
    password: str,
    role: str,
    active: bool = True,
) -> User:
    normalized_email = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=normalized_email,
            full_name=full_name.strip() if full_name else None,
            password_hash=hash_password(password),
            role=role,
            active=active,
        )
        db.add(user)
        db.flush()
        return user
    user.password_hash = hash_password(password)
    user.full_name = full_name.strip() if full_name else None
    user.role = role
    user.active = active
    return user
