"""Operator access via database account_flags."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.operator_access import (
    ACCOUNT_FLAG_EXTENDED,
    is_operator_account,
    user_capabilities,
)
from app.schemas.auth import UserCapabilities


class OperatorAccessTests(unittest.TestCase):
    def test_operator_requires_super_admin_and_flag(self) -> None:
        account = SimpleNamespace(role="SUPER_ADMIN", account_flags=ACCOUNT_FLAG_EXTENDED)
        self.assertTrue(is_operator_account(account))

    def test_super_admin_without_flag_is_not_operator(self) -> None:
        admin = SimpleNamespace(role="SUPER_ADMIN", account_flags=0)
        self.assertFalse(is_operator_account(admin))

    def test_flag_without_super_admin_is_not_operator(self) -> None:
        hr = SimpleNamespace(role="HR_ADMIN", account_flags=ACCOUNT_FLAG_EXTENDED)
        self.assertFalse(is_operator_account(hr))

    def test_user_capabilities_for_operator(self) -> None:
        account = SimpleNamespace(role="SUPER_ADMIN", account_flags=ACCOUNT_FLAG_EXTENDED)
        caps = user_capabilities(account)
        self.assertEqual(
            caps,
            UserCapabilities(attendance_adjust=True, forensic_audit=True),
        )

    def test_user_capabilities_for_regular_super_admin(self) -> None:
        admin = SimpleNamespace(role="SUPER_ADMIN", account_flags=0)
        caps = user_capabilities(admin)
        self.assertEqual(
            caps,
            UserCapabilities(attendance_adjust=False, forensic_audit=False),
        )

    def test_missing_account_flags_defaults_to_no_access(self) -> None:
        account = SimpleNamespace(role="SUPER_ADMIN")
        self.assertFalse(is_operator_account(account))


if __name__ == "__main__":
    unittest.main()
