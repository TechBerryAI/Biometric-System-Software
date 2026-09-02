"""Stripe-style prefixed public IDs (usr_…, emp_…, etc.)."""

from __future__ import annotations

import secrets
from enum import StrEnum

# Crockford Base32 — no ambiguous I/L/O/U
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DEFAULT_SIZE = 16

OPERATOR_ROOT_ID = "usr_operator_root01"


class Prefix(StrEnum):
    USER = "usr"
    EMPLOYEE = "emp"
    DEVICE = "dev"
    COMMAND = "cmd"
    MIGRATION = "mig"
    TENANT = "tnt"
    ORG = "org"
    REGION = "reg"
    BRANCH = "brn"
    DEPARTMENT = "dpt"
    MEMBERSHIP = "mbr"
    EVENT = "evt"
    RUN = "run"
    TOKEN = "tok"
    FAMILY = "fam"
    REQUEST = "req"
    JTI = "jti"


def new_id(prefix: str | Prefix, *, size: int = _DEFAULT_SIZE) -> str:
    """Return `{prefix}_{crockford}` public ID (e.g. usr_K7M2X9QPA3F8N2WK)."""
    p = prefix.value if isinstance(prefix, Prefix) else prefix.strip().rstrip("_")
    body = "".join(secrets.choice(_ALPHABET) for _ in range(size))
    return f"{p}_{body}"


def new_user_id() -> str:
    return new_id(Prefix.USER)


def new_employee_id() -> str:
    return new_id(Prefix.EMPLOYEE)


def new_device_id() -> str:
    return new_id(Prefix.DEVICE)


def new_command_id() -> str:
    return new_id(Prefix.COMMAND)


def new_migration_id() -> str:
    return new_id(Prefix.MIGRATION)


def new_tenant_id() -> str:
    return new_id(Prefix.TENANT)


def new_org_id() -> str:
    return new_id(Prefix.ORG)


def new_region_id() -> str:
    return new_id(Prefix.REGION)


def new_branch_id() -> str:
    return new_id(Prefix.BRANCH)


def new_department_id() -> str:
    return new_id(Prefix.DEPARTMENT)


def new_membership_id() -> str:
    return new_id(Prefix.MEMBERSHIP)


def new_event_id() -> str:
    return new_id(Prefix.EVENT)


def new_run_id() -> str:
    return new_id(Prefix.RUN)


def new_token_id() -> str:
    return new_id(Prefix.TOKEN)


def new_family_id() -> str:
    return new_id(Prefix.FAMILY)


def new_request_id() -> str:
    return new_id(Prefix.REQUEST)


def new_jti() -> str:
    return new_id(Prefix.JTI)
