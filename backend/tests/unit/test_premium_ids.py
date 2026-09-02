"""Unit tests for Stripe-style public ID generation."""

from __future__ import annotations

import re

import pytest

from app.shared.ids import OPERATOR_ROOT_ID, Prefix, new_id, new_user_id


_CROCKFORD = re.compile(r"^[0-9A-HJKMNP-TV-Z]+$")


@pytest.mark.testid("BE-UNIT-ID-001")
def test_new_id_format() -> None:
    value = new_user_id()
    assert value.startswith("usr_")
    body = value.split("_", 1)[1]
    assert len(body) == 16
    assert _CROCKFORD.match(body)


@pytest.mark.testid("BE-UNIT-ID-002")
def test_new_id_unique() -> None:
    assert new_id(Prefix.EMPLOYEE) != new_id(Prefix.EMPLOYEE)


@pytest.mark.testid("BE-UNIT-ID-003")
def test_operator_root_id() -> None:
    assert OPERATOR_ROOT_ID == "usr_operator_root01"
    assert len(OPERATOR_ROOT_ID) <= 40
