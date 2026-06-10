"""GOD mode account constants (reserved bootstrap super-admin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

GOD_MODE_EMAIL = "techberryaiteam@gmail.com"


class _GodModeUser(Protocol):
    email: str | None
    role: str | None


if TYPE_CHECKING:
    from app.models.user import User


def is_god_mode_email(email: str | None) -> bool:
    return (email or "").strip().lower() == GOD_MODE_EMAIL


def is_god_mode_user(user: _GodModeUser | None) -> bool:
    """True only for the reserved bootstrap SUPER_ADMIN account."""
    if user is None:
        return False
    return user.role == "SUPER_ADMIN" and is_god_mode_email(user.email)