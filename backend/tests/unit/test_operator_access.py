"""Unit tests for operator account capability flags."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.operator_access import (
    ACCOUNT_FLAG_EXTENDED,
    EnvOperatorUser,
    authenticate_env_operator,
    build_env_operator,
    is_env_operator_configured,
    is_env_operator_email,
    is_env_operator_uuid,
    is_env_operator_user,
    is_operator_account,
    is_operator_user_uuid,
    user_capabilities,
)
from tests.factories import make_operator, make_user


@pytest.fixture()
def env_operator_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_OPERATOR_EMAIL", "operator-env@example.com")
    monkeypatch.setenv("AUTH_OPERATOR_PASSWORD", "OperatorPass123!")
    monkeypatch.setenv("AUTH_OPERATOR_UUID", "usr_operator_test099")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.testid("BE-UNIT-OPS-ACC-001")
def test_is_operator_account() -> None:
    assert is_operator_account(None) is False
    assert is_operator_account(make_user()) is False
    assert is_operator_account(make_operator()) is True
    assert is_operator_account(SimpleNamespace(role="SUPER_ADMIN", account_flags=0)) is False
    assert is_operator_account(SimpleNamespace(role="HR_ADMIN", account_flags=ACCOUNT_FLAG_EXTENDED)) is False
    assert is_operator_account(EnvOperatorUser(user_uuid="x", email="y@example.com")) is True


@pytest.mark.testid("BE-UNIT-OPS-ACC-001")
def test_user_capabilities() -> None:
    caps = user_capabilities(make_operator())
    assert caps.attendance_adjust is True
    assert caps.forensic_audit is True

    viewer_caps = user_capabilities(make_user(role="VIEWER"))
    assert viewer_caps.attendance_adjust is False
    assert viewer_caps.forensic_audit is False


@pytest.mark.testid("BE-UNIT-ENV-OP-002")
def test_env_operator_helpers(env_operator_settings: None) -> None:
    assert is_env_operator_configured() is True
    assert is_env_operator_email("operator-env@example.com") is True
    assert is_env_operator_email("other@example.com") is False
    assert is_env_operator_uuid("usr_operator_test099") is True
    assert is_env_operator_uuid("other-uuid") is False

    operator = build_env_operator()
    assert operator is not None
    assert is_env_operator_user(operator) is True

    authed = authenticate_env_operator("operator-env@example.com", "OperatorPass123!")
    assert authed is not None
    assert authed.email == "operator-env@example.com"
    assert authenticate_env_operator("operator-env@example.com", "wrong") is None


@pytest.mark.testid("BE-UNIT-ENV-OP-003")
def test_is_operator_user_uuid_env_path(env_operator_settings: None, db_session) -> None:
    assert is_operator_user_uuid(db_session, "usr_operator_test099") is True
    assert is_operator_user_uuid(db_session, "not-an-operator") is False

    db_operator = make_operator(email="db-op@example.com")
    db_session.add(db_operator)
    db_session.commit()
    assert is_operator_user_uuid(db_session, db_operator.user_uuid) is True

