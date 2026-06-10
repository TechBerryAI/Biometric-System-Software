"""GOD mode account guard tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.god_mode import GOD_MODE_EMAIL, is_god_mode_user


class GodModeTests(unittest.TestCase):
    def test_god_mode_requires_super_admin_and_reserved_email(self) -> None:
        god = SimpleNamespace(role="SUPER_ADMIN", email=GOD_MODE_EMAIL)
        self.assertTrue(is_god_mode_user(god))

    def test_other_super_admin_is_not_god_mode(self) -> None:
        admin = SimpleNamespace(role="SUPER_ADMIN", email="other@example.com")
        self.assertFalse(is_god_mode_user(admin))

    def test_reserved_email_without_super_admin_is_not_god_mode(self) -> None:
        hr = SimpleNamespace(role="HR_ADMIN", email=GOD_MODE_EMAIL)
        self.assertFalse(is_god_mode_user(hr))


if __name__ == "__main__":
    unittest.main()
