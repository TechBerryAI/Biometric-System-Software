"""Reserved privileged account guard tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.privileged_account import is_privileged_account, privileged_account_email


class PrivilegedAccountTests(unittest.TestCase):
    def test_privileged_account_requires_super_admin_and_reserved_email(self) -> None:
        account = SimpleNamespace(role="SUPER_ADMIN", email=privileged_account_email())
        self.assertTrue(is_privileged_account(account))

    def test_other_super_admin_is_not_privileged(self) -> None:
        admin = SimpleNamespace(role="SUPER_ADMIN", email="other@example.com")
        self.assertFalse(is_privileged_account(admin))

    def test_reserved_email_without_super_admin_is_not_privileged(self) -> None:
        hr = SimpleNamespace(role="HR_ADMIN", email=privileged_account_email())
        self.assertFalse(is_privileged_account(hr))


if __name__ == "__main__":
    unittest.main()
