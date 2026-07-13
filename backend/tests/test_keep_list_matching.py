"""Tests for organization roster name matching."""

from app.constants.keep_list import match_employee_to_roster


def test_code_match() -> None:
    m = match_employee_to_roster(device_user_id="TBC278", name="Chetan Gore")
    assert m is not None
    assert m.match_kind == "code"


def test_first_last_name_match_chetan() -> None:
    m = match_employee_to_roster(device_user_id="TBI280", name="Chetan Gore")
    assert m is not None
    assert m.roster_code == "TBC278"
    assert m.match_kind == "first_last_name"


def test_rahul_roshan_wrong_code() -> None:
    m = match_employee_to_roster(device_user_id="TBI132", name="Rahul Roshan")
    assert m is not None
    assert m.roster_code == "TBC132"


def test_first_name_unique_kunal() -> None:
    m = match_employee_to_roster(device_user_id="2", name="Kunal")
    assert m is not None
    assert m.roster_code == "TBI349"


def test_yogesh_joshi_not_bhimsen() -> None:
    m = match_employee_to_roster(device_user_id="TBI070", name="Yogesh Joshi")
    assert m is None


def test_mohammed_truncated() -> None:
    m = match_employee_to_roster(device_user_id="TBI281", name="Mohammed Sohail Yakub Ku")
    assert m is not None
    assert m.roster_code == "TBI389"


def test_placeholder_user_prefix_ignored() -> None:
    m = match_employee_to_roster(device_user_id="TBI999", name="User TBI311")
    assert m is None
