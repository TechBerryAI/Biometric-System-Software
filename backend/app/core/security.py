"""Authentication, JWT utilities, RBAC, and auth dependencies."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.operator_access import is_operator_account
from app.domains.auth.models.user import User
from app.domains.auth.services.cookie_auth_service import resolve_access_token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


class Permission:
    USER_MANAGE = "user:manage"
    EMPLOYEE_VIEW = "employee:view"
    EMPLOYEE_EDIT = "employee:edit"
    DEVICE_MANAGE = "device:manage"
    SYNC_TRIGGER = "sync:trigger"
    AI_ADMIN = "ai:admin"
    REPORT_READ = "reports:read"
    AUDIT_READ = "audit:read"
    METRICS_READ = "metrics:read"
    ANOMALY_MANAGE = "anomaly:manage"


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "SUPER_ADMIN": {
        Permission.USER_MANAGE,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_EDIT,
        Permission.DEVICE_MANAGE,
        Permission.SYNC_TRIGGER,
        Permission.AI_ADMIN,
        Permission.REPORT_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
        Permission.ANOMALY_MANAGE,
    },
    "HR_ADMIN": {
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_EDIT,
        Permission.SYNC_TRIGGER,
        Permission.REPORT_READ,
        Permission.ANOMALY_MANAGE,
    },
    "IT_ADMIN": {
        Permission.USER_MANAGE,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_EDIT,
        Permission.DEVICE_MANAGE,
        Permission.SYNC_TRIGGER,
        Permission.REPORT_READ,
        Permission.ANOMALY_MANAGE,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
    },
    "CEO": {
        Permission.SYNC_TRIGGER,
        Permission.REPORT_READ,
        Permission.EMPLOYEE_VIEW,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
    },
    "MANAGER": {
        Permission.EMPLOYEE_VIEW,
        Permission.REPORT_READ,
        Permission.SYNC_TRIGGER,
    },
    "VIEWER": {
        Permission.EMPLOYEE_VIEW,
        Permission.REPORT_READ,
    },
    "DEVICE_OPERATOR": {
        Permission.DEVICE_MANAGE,
        Permission.SYNC_TRIGGER,
        Permission.METRICS_READ,
    },
}

ALLOWED_APP_ROLES = {"SUPER_ADMIN", "HR_ADMIN", "IT_ADMIN", "CEO"}


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _token_expiry(minutes: int) -> datetime:
    return _utcnow() + timedelta(minutes=minutes)


def create_access_token(*, user_uuid: str, role: str, email: str) -> tuple[str, datetime]:
    settings = get_settings()
    expire = _token_expiry(settings.access_token_expire_minutes)
    payload = {
        "sub": user_uuid,
        "email": email,
        "role": role,
        "type": "access",
        "jti": str(uuid4()),
        "exp": int(expire.timestamp()),
        "iat": int(_utcnow().timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expire


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    if not settings.auth_enabled:
        user = db.execute(select(User).where(User.active.is_(True)).order_by(User.id)).scalars().first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth disabled but no active users exist.",
            )
        return user

    bearer_token = credentials.credentials if credentials is not None else None
    token = resolve_access_token(request, bearer_token)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user_uuid = payload.get("sub")
    if not user_uuid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.execute(select(User).where(User.user_uuid == user_uuid)).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or missing")
    if user.role not in ALLOWED_APP_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account role is not allowed to access the app.")
    return user


def require_permissions(*required_permissions: str):
    def _dependency(user: User = Depends(get_current_user)) -> User:
        granted = ROLE_PERMISSIONS.get(user.role, set())
        missing = [perm for perm in required_permissions if perm not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing)}",
            )
        return user

    return _dependency


def require_operator_account(user: User = Depends(get_current_user)) -> User:
    if not is_operator_account(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )
    return user
