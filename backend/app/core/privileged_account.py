"""Reserved bootstrap super-admin account (internal)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.core.config import Settings, get_settings

_DEFAULT_PRIVILEGED_EMAIL = "techberryaiteam@gmail.com"


class _PrivilegedAccountUser(Protocol):
    email: str | None
    role: str | None


if TYPE_CHECKING:
    from app.models.user import User


def privileged_account_email(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    raw = (cfg.privileged_account_email or _DEFAULT_PRIVILEGED_EMAIL).strip().lower()
    return raw or _DEFAULT_PRIVILEGED_EMAIL


def is_privileged_email(email: str | None, settings: Settings | None = None) -> bool:
    return (email or "").strip().lower() == privileged_account_email(settings)


def is_privileged_account(user: _PrivilegedAccountUser | None, settings: Settings | None = None) -> bool:
    if user is None:
        return False
    return user.role == "SUPER_ADMIN" and is_privileged_email(user.email, settings)
