"""Widen public IDs and remap UUID v4 values to Stripe-style prefixed IDs.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-02

Replaces opaque UUID strings (e.g. ca05c6ff-…) with premium IDs
(usr_…, emp_…, etc.). Invalidates refresh tokens so users re-login.
Update AUTH_OPERATOR_UUID to usr_operator_root01 before/after upgrade.
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.shared.ids import (
    OPERATOR_ROOT_ID,
    Prefix,
    new_id,
)

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Known legacy env-operator subjects → stable premium ID
_KNOWN_OPERATOR_UUIDS = {
    "00000000-0000-4000-8000-000000000001",
    "ae5952f1-2a4d-45cd-9866-5a6e0d2ed8b3",
}

# (table, column) — public identity + reference columns to widen to VARCHAR(40)
_WIDEN_COLUMNS: list[tuple[str, str]] = [
    ("users", "user_uuid"),
    ("employees", "employee_uuid"),
    ("devices", "device_uuid"),
    ("device_commands", "command_uuid"),
    ("device_commands", "initiated_by"),
    ("device_commands", "audit_event_uuid"),
    ("device_migrations", "migration_uuid"),
    ("device_migrations", "created_by"),
    ("device_migrations", "approved_by"),
    ("device_migration_items", "employee_uuid"),
    ("device_migration_items", "command_uuid"),
    ("tenants", "tenant_uuid"),
    ("organizations", "org_uuid"),
    ("regions", "region_uuid"),
    ("branches", "branch_uuid"),
    ("departments", "dept_uuid"),
    ("tenant_memberships", "membership_uuid"),
    ("tenant_memberships", "user_uuid"),
    ("audit_events", "event_uuid"),
    ("audit_events", "actor_user_uuid"),
    ("audit_events", "request_id"),
    ("attendance_archive_runs", "run_uuid"),
    ("refresh_tokens", "token_id"),
    ("refresh_tokens", "family_id"),
    ("attendance_logs", "employee_uuid"),
    ("device_user_mappings", "employee_uuid"),
    ("device_user_drift", "employee_uuid"),
    ("device_user_drift", "command_uuid"),
    ("system_control_state", "changed_by"),
]

_PARENT_REMAPS: list[tuple[str, str, str, Prefix]] = [
    # table, pk_col, uuid_col, prefix
    ("users", "id", "user_uuid", Prefix.USER),
    ("employees", "id", "employee_uuid", Prefix.EMPLOYEE),
    ("devices", "id", "device_uuid", Prefix.DEVICE),
    ("device_commands", "id", "command_uuid", Prefix.COMMAND),
    ("device_migrations", "id", "migration_uuid", Prefix.MIGRATION),
    ("tenants", "id", "tenant_uuid", Prefix.TENANT),
    ("organizations", "id", "org_uuid", Prefix.ORG),
    ("regions", "id", "region_uuid", Prefix.REGION),
    ("branches", "id", "branch_uuid", Prefix.BRANCH),
    ("departments", "id", "dept_uuid", Prefix.DEPARTMENT),
    ("tenant_memberships", "id", "membership_uuid", Prefix.MEMBERSHIP),
    ("audit_events", "id", "event_uuid", Prefix.EVENT),
    ("attendance_archive_runs", "id", "run_uuid", Prefix.RUN),
]

# After parent maps exist: (table, column, map_key)
_REF_REMAPS: list[tuple[str, str, str]] = [
    ("tenant_memberships", "user_uuid", "user"),
    ("audit_events", "actor_user_uuid", "user"),
    ("device_commands", "initiated_by", "user"),
    ("device_migrations", "created_by", "user"),
    ("device_migrations", "approved_by", "user"),
    ("system_control_state", "changed_by", "user"),
    ("attendance_logs", "employee_uuid", "employee"),
    ("device_user_mappings", "employee_uuid", "employee"),
    ("device_user_drift", "employee_uuid", "employee"),
    ("device_migration_items", "employee_uuid", "employee"),
    ("device_user_drift", "command_uuid", "command"),
    ("device_migration_items", "command_uuid", "command"),
    ("device_commands", "audit_event_uuid", "event"),
]

_ENTITY_KEY = {
    "users": "user",
    "employees": "employee",
    "devices": "device",
    "device_commands": "command",
    "device_migrations": "migration",
    "tenants": "tenant",
    "organizations": "org",
    "regions": "region",
    "branches": "branch",
    "departments": "department",
    "tenant_memberships": "membership",
    "audit_events": "event",
    "attendance_archive_runs": "run",
}


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _looks_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _needs_remap(value: str | None, prefix: str) -> bool:
    if not value:
        return False
    if value.startswith(f"{prefix}_") and not _looks_uuid(value):
        return False
    return True


def _drop_employee_fks(conn) -> None:
    inspector = sa.inspect(conn)
    for table, expected in (
        ("attendance_logs", "employees"),
        ("device_user_mappings", "employees"),
    ):
        if table not in _tables(conn):
            continue
        for fk in inspector.get_foreign_keys(table):
            referred = fk.get("referred_table")
            cols = fk.get("constrained_columns") or []
            name = fk.get("name")
            if referred == expected and "employee_uuid" in cols and name:
                op.drop_constraint(name, table, type_="foreignkey")


def _widen(conn) -> None:
    existing = _tables(conn)
    for table, column in _WIDEN_COLUMNS:
        if table not in existing:
            continue
        if column not in _columns(conn, table):
            continue
        op.execute(
            text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(40)")
        )


def _remap_parents(conn) -> dict[str, dict[str, str]]:
    """Return maps[entity_key][old_id] = new_id and UPDATE parent rows."""
    maps: dict[str, dict[str, str]] = {k: {} for k in _ENTITY_KEY.values()}
    # Seed known operator subjects
    for old in _KNOWN_OPERATOR_UUIDS:
        maps["user"][old] = OPERATOR_ROOT_ID

    existing = _tables(conn)
    for table, pk_col, uuid_col, prefix in _PARENT_REMAPS:
        if table not in existing:
            continue
        entity = _ENTITY_KEY[table]
        rows = conn.execute(text(f"SELECT {pk_col}, {uuid_col} FROM {table}")).fetchall()
        for pk, old in rows:
            if old is None:
                continue
            if old in maps[entity]:
                new = maps[entity][old]
            elif not _needs_remap(old, prefix.value):
                maps[entity][old] = old
                continue
            else:
                new = new_id(prefix)
                maps[entity][old] = new
            if new != old:
                conn.execute(
                    text(f"UPDATE {table} SET {uuid_col} = :new WHERE {pk_col} = :pk"),
                    {"new": new, "pk": pk},
                )
    return maps


def _remap_refs(conn, maps: dict[str, dict[str, str]]) -> None:
    existing = _tables(conn)
    for table, column, map_key in _REF_REMAPS:
        if table not in existing:
            continue
        if column not in _columns(conn, table):
            continue
        mapping = maps.get(map_key) or {}
        if not mapping:
            continue
        # Also apply operator known map for user refs
        rows = conn.execute(
            text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL")
        ).fetchall()
        for (old,) in rows:
            new = mapping.get(old)
            if new is None and map_key == "user" and old in _KNOWN_OPERATOR_UUIDS:
                new = OPERATOR_ROOT_ID
            if new is None and _looks_uuid(old) and map_key == "user":
                # Orphan actor UUID (e.g. deleted user / old operator) — assign premium once
                new = new_id(Prefix.USER)
                mapping[old] = new
            if new is None:
                continue
            if new == old:
                continue
            conn.execute(
                text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),
                {"new": new, "old": old},
            )


def _remap_request_ids(conn) -> None:
    if "audit_events" not in _tables(conn):
        return
    if "request_id" not in _columns(conn, "audit_events"):
        return
    rows = conn.execute(
        text("SELECT id, request_id FROM audit_events WHERE request_id IS NOT NULL")
    ).fetchall()
    for pk, old in rows:
        if not _needs_remap(old, Prefix.REQUEST.value):
            continue
        conn.execute(
            text("UPDATE audit_events SET request_id = :new WHERE id = :pk"),
            {"new": new_id(Prefix.REQUEST), "pk": pk},
        )


def _recreate_employee_fks(conn) -> None:
    existing = _tables(conn)
    if "attendance_logs" in existing and "employees" in existing:
        op.create_foreign_key(
            "fk_attendance_logs_employee_uuid_employees",
            "attendance_logs",
            "employees",
            ["employee_uuid"],
            ["employee_uuid"],
            ondelete="SET NULL",
        )
    if "device_user_mappings" in existing and "employees" in existing:
        op.create_foreign_key(
            "fk_device_user_mappings_employee_uuid_employees",
            "device_user_mappings",
            "employees",
            ["employee_uuid"],
            ["employee_uuid"],
            ondelete="CASCADE",
        )


def _clear_refresh_tokens(conn) -> None:
    if "refresh_tokens" in _tables(conn):
        op.execute(text("DELETE FROM refresh_tokens"))


def upgrade() -> None:
    conn = op.get_bind()
    _drop_employee_fks(conn)
    _widen(conn)
    maps = _remap_parents(conn)
    _remap_refs(conn, maps)
    _remap_request_ids(conn)
    _recreate_employee_fks(conn)
    _clear_refresh_tokens(conn)


def downgrade() -> None:
    # Irreversible data remap — only shrink widths if values still fit (unsafe).
    # No-op for data; leave VARCHAR(40) in place.
    pass
