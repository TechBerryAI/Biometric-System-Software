"""Unit tests for organization keep-list roster matching."""

from __future__ import annotations

import pytest

from app.shared.keep_list import match_employee_to_roster


@pytest.mark.testid("BE-UNIT-KEEP-001")
def test_match_by_device_code_tbi001() -> None:
    match = match_employee_to_roster(device_user_id="TBI001", name="Anything")
    assert match is not None
    assert match.match_kind == "code"
    assert match.roster_code == "TBI001"
    assert match.roster_name == "Unmesh Tari"


@pytest.mark.testid("BE-UNIT-KEEP-001")
def test_match_by_exact_name() -> None:
    match = match_employee_to_roster(device_user_id="UNKNOWN99", name="Unmesh Tari")
    assert match is not None
    assert match.match_kind == "exact_name"
    assert match.roster_code == "TBI001"


@pytest.mark.testid("BE-UNIT-KEEP-001")
def test_placeholder_name_no_match() -> None:
    assert match_employee_to_roster(device_user_id="GUEST1", name="") is None
    assert match_employee_to_roster(device_user_id="GUEST1", name="   ") is None


@pytest.mark.testid("BE-UNIT-KEEP-001")
def test_yogesh_false_positive_pair_no_match() -> None:
    """'Yogesh Joshi' must not keep-match 'Yogesh Bhimsen Joshi' via first+last alone."""
    match = match_employee_to_roster(device_user_id="ORPHAN", name="Yogesh Joshi")
    assert match is None
