"""Unit tests for RBAC permission matrix."""

from __future__ import annotations

import pytest

from app.core.security import ROLE_PERMISSIONS, Permission


@pytest.mark.testid("BE-UNIT-SEC-001")
def test_super_admin_has_all_key_permissions() -> None:
    granted = ROLE_PERMISSIONS["SUPER_ADMIN"]
    for perm in (
        Permission.USER_MANAGE,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_EDIT,
        Permission.DEVICE_MANAGE,
        Permission.SYNC_TRIGGER,
        Permission.AI_ADMIN,
        Permission.REPORT_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
        Permission.ANOMALY_MANAGE,
    ):
        assert perm in granted


@pytest.mark.testid("BE-UNIT-SEC-001")
def test_viewer_has_empty_permissions() -> None:
    assert ROLE_PERMISSIONS["VIEWER"] == set()


@pytest.mark.testid("BE-UNIT-SEC-001")
def test_require_permissions_concept_via_matrix() -> None:
    """require_permissions() denies when any required perm is missing from ROLE_PERMISSIONS."""
    required = (Permission.DEVICE_MANAGE, Permission.AI_ADMIN)
    hr = ROLE_PERMISSIONS["HR_ADMIN"]
    missing = [p for p in required if p not in hr]
    assert Permission.DEVICE_MANAGE in missing
    assert Permission.AI_ADMIN in missing

    admin_missing = [p for p in required if p not in ROLE_PERMISSIONS["SUPER_ADMIN"]]
    assert admin_missing == []
