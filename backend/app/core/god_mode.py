"""GOD mode account constants (reserved bootstrap super-admin)."""

from __future__ import annotations

GOD_MODE_EMAIL = "techberryaiteam@gmail.com"


def is_god_mode_email(email: str | None) -> bool:
    return (email or "").strip().lower() == GOD_MODE_EMAIL
