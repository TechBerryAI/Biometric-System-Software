"""Unit tests for operator account capability flags."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.operator_access import ACCOUNT_FLAG_EXTENDED, is_operator_account, user_capabilities
from tests.factories import make_operator, make_user


@pytest.mark.testid("BE-UNIT-OPS-ACC-001")
def test_is_operator_account() -> None:
    assert is_operator_account(None) is False
    assert is_operator_account(make_user()) is False
    assert is_operator_account(make_operator()) is True
    assert is_operator_account(SimpleNamespace(role="SUPER_ADMIN", account_flags=0)) is False
    assert is_operator_account(SimpleNamespace(role="HR_ADMIN", account_flags=ACCOUNT_FLAG_EXTENDED)) is False


@pytest.mark.testid("BE-UNIT-OPS-ACC-001")
def test_user_capabilities() -> None:
    caps = user_capabilities(make_operator())
    assert caps.attendance_adjust is True
    assert caps.forensic_audit is True

    viewer_caps = user_capabilities(make_user(role="VIEWER"))
    assert viewer_caps.attendance_adjust is False
    assert viewer_caps.forensic_audit is False
