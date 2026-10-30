"""Authentication workflows: login throttling, rotation, and admin bootstrap."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.operator_access import (
    AuthPrincipal,
    EnvOperatorUser,
    SessionStoreUnavailable,
    authenticate_env_operator,
    is_env_operator_email,
    is_env_operator_user,
    operator_refresh_expiry,
    revoke_operator_refresh_token,
    rotate_operator_refresh_token,
    store_operator_refresh_token,
)
from app.core.redis_keys import with_namespace
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.domains.auth.models.password_reset_token import PasswordResetToken
from app.domains.auth.models.refresh_token import RefreshToken
from app.domains.auth.models.user import User, UserRole
from app.domains.auth.services.password_reset_mailer import send_password_reset_email
from app.shared.ids import new_family_id

ALLOWED_APP_ROLES = {
    UserRole.SUPER_ADMIN.value,
    UserRole.HR_ADMIN.value,
    UserRole.IT_ADMIN.value,
    UserRole.CEO.value,
}


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


class LoginRateLimiter:
    def __init__(self, settings: Settings | None = None, *, key_prefix: str = "auth:login:fail") -> None:
        self._settings = settings or get_settings()
        self._key_prefix = key_prefix
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
        key = f"{self._key_prefix}:{email.strip().lower()}"
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


def authenticate_user(db: Session, email: str, password: str) -> AuthPrincipal | None:
    normalized_email = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is not None:
        if not user.active:
            return None
        if user.role not in ALLOWED_APP_ROLES:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user
    return authenticate_env_operator(normalized_email, password)


def _issue_operator_session_tokens(
    operator: EnvOperatorUser,
    family_id: str,
) -> tuple[str, str, datetime]:
    access_token, _ = create_access_token(
        user_uuid=operator.user_uuid,
        role=operator.role,
        email=operator.email,
    )
    refresh_token = generate_refresh_token()
    refresh_expiry = operator_refresh_expiry()
    token_hash = hash_refresh_token(refresh_token)
    if not store_operator_refresh_token(
        token_hash=token_hash,
        family_id=family_id,
        expires_at=refresh_expiry,
    ):
        raise SessionStoreUnavailable("Operator refresh token store unavailable.")
    return access_token, refresh_token, refresh_expiry


def issue_session_tokens(
    db: Session,
    user: AuthPrincipal,
    *,
    family_id: str | None = None,
) -> tuple[str, str, datetime]:
    settings = get_settings()
    token_family = family_id or new_family_id()

    if is_env_operator_user(user):
        return _issue_operator_session_tokens(user, token_family)

    access_token, _ = create_access_token(user_uuid=user.user_uuid, role=user.role, email=user.email)
    refresh_token = generate_refresh_token()
    refresh_expiry = _utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expiry,
            revoked=False,
            family_id=token_family,
        )
    )
    user.last_login = _utcnow()
    return access_token, refresh_token, refresh_expiry


def _revoke_token_family(db: Session, family_id: str) -> None:
    now = _utcnow()
    tokens = db.execute(
        select(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False))
    ).scalars()
    for token in tokens:
        token.revoked = True
        token.revoked_at = now


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[AuthPrincipal, str, str, datetime] | None:
    token_hash = hash_refresh_token(raw_refresh_token)
    refresh = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if refresh is None:
        return rotate_operator_refresh_token(
            raw_refresh_token,
            lambda operator, fam: _issue_operator_session_tokens(operator, fam),
        )

    if refresh.revoked:
        if refresh.family_id:
            _revoke_token_family(db, refresh.family_id)
            db.flush()
        return None

    if _as_utc(refresh.expires_at) <= _as_utc(_utcnow()):
        return None

    user = db.get(User, refresh.user_id)
    if user is None or not user.active:
        return None

    refresh.revoked = True
    refresh.revoked_at = _utcnow()
    access_token, new_refresh, refresh_expiry = issue_session_tokens(db, user, family_id=refresh.family_id)
    return user, access_token, new_refresh, refresh_expiry


def revoke_refresh_token(db: Session, raw_refresh_token: str) -> bool:
    token_hash = hash_refresh_token(raw_refresh_token)
    refresh = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if refresh is None:
        return revoke_operator_refresh_token(raw_refresh_token)
    refresh.revoked = True
    refresh.revoked_at = _utcnow()
    return True


def revoke_all_user_refresh_tokens(db: Session, user_id: int) -> int:
    tokens = db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
    ).scalars()
    count = 0
    for token in tokens:
        token.revoked = True
        token.revoked_at = _utcnow()
        count += 1
    return count


def change_user_password(db: Session, user: User, current_password: str, new_password: str) -> bool:
    if not verify_password(current_password, user.password_hash):
        return False
    user.password_hash = hash_password(new_password)
    revoke_all_user_refresh_tokens(db, user.id)
    return True


def _invalidate_unused_reset_tokens(db: Session, user_id: int) -> None:
    now = _utcnow()
    tokens = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
    ).scalars()
    for token in tokens:
        token.used_at = now


def generate_password_reset_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_password_reset_otp(user_id: int, otp: str) -> str:
    return hash_refresh_token(f"{user_id}:{otp.strip()}")


def request_password_reset(db: Session, email: str) -> bool:
    """Email a one-time OTP only when an existing, eligible login account matches.

    Never creates a user. Returns True only after an OTP is stored for that account.
    """
    normalized_email = email.strip().lower()
    if is_env_operator_email(normalized_email):
        return False

    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None or not user.active or user.role not in ALLOWED_APP_ROLES:
        return False

    settings = get_settings()
    otp = generate_password_reset_otp()
    _invalidate_unused_reset_tokens(db, user.id)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_otp(user.id, otp),
            expires_at=_utcnow() + timedelta(minutes=settings.password_reset_expire_minutes),
        )
    )
    db.flush()

    send_password_reset_email(
        recipient=user.email,
        otp=otp,
        recipient_name=user.full_name,
    )
    return True


def reset_password_with_otp(db: Session, email: str, otp: str, new_password: str) -> User | None:
    normalized_email = email.strip().lower()
    digits = otp.strip()
    if not digits.isdigit() or len(digits) != 6:
        return None
    if is_env_operator_email(normalized_email):
        return None

    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None or not user.active or user.role not in ALLOWED_APP_ROLES:
        return None

    token_hash = hash_password_reset_otp(user.id, digits)
    reset = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == token_hash,
        )
    ).scalar_one_or_none()
    if reset is None or reset.used_at is not None:
        return None
    if _as_utc(reset.expires_at) <= _as_utc(_utcnow()):
        return None
    if verify_password(new_password, user.password_hash):
        raise ValueError("New password must differ from current password")

    user.password_hash = hash_password(new_password)
    revoke_all_user_refresh_tokens(db, user.id)
    reset.used_at = _utcnow()
    _invalidate_unused_reset_tokens(db, user.id)
    return user


def ensure_bootstrap_admin(db: Session) -> User | None:
    settings = get_settings()
    if not settings.auth_bootstrap_admin_email or not settings.auth_bootstrap_admin_password:
        return None
    normalized_email = settings.auth_bootstrap_admin_email.strip().lower()
    if is_env_operator_email(normalized_email):
        return None
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
    if is_env_operator_email(normalized_email):
        raise ValueError("This email is reserved for the env-backed operator account.")
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
