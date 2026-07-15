"""Canonicalize single-IP device labels into ZK_DEVICE_ID / main-entrance.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-15

Two registry rows pointed at the same ZK terminal (Workplace Entrance + main-entrance).
This migration remaps alias device_id values onto one canonical id and deactivates
duplicate devices rows for that IP.
"""

from __future__ import annotations

import os
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CANONICAL = os.environ.get("ZK_DEVICE_ID", "main-entrance").strip() or "main-entrance"
_LEGACY_ALIASES = ("Workplace Entrance", "workplace-entrance", "WorkplaceEntrance")


def _names_as_values(names: Sequence[str]) -> str:
    """Build a SQL VALUES list for string names (escaped)."""
    parts = []
    for name in names:
        escaped = name.replace("'", "''")
        parts.append(f"('{escaped}')")
    return ", ".join(parts)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    canonical = _CANONICAL

    canonical_ip = None
    if "devices" in tables:
        row = conn.execute(
            sa.text("SELECT ip_address FROM devices WHERE name = :name LIMIT 1"),
            {"name": canonical},
        ).first()
        if row is None:
            for alias in _LEGACY_ALIASES:
                row = conn.execute(
                    sa.text("SELECT ip_address FROM devices WHERE name = :name LIMIT 1"),
                    {"name": alias},
                ).first()
                if row is not None:
                    break
        if row is not None:
            canonical_ip = row[0]

    alias_names: set[str] = set(_LEGACY_ALIASES)
    if "devices" in tables and canonical_ip:
        siblings = conn.execute(
            sa.text(
                "SELECT name FROM devices WHERE ip_address = :ip AND name <> :canonical"
            ),
            {"ip": canonical_ip, "canonical": canonical},
        ).fetchall()
        alias_names.update(r[0] for r in siblings if r[0])

    alias_names.discard(canonical)
    if not alias_names:
        return

    if "devices" in tables:
        has_canonical = conn.execute(
            sa.text("SELECT 1 FROM devices WHERE name = :name LIMIT 1"),
            {"name": canonical},
        ).first()
        if has_canonical is None:
            donor = None
            for alias in sorted(alias_names):
                donor = conn.execute(
                    sa.text(
                        "SELECT ip_address, port, timezone, location FROM devices "
                        "WHERE name = :name ORDER BY id LIMIT 1"
                    ),
                    {"name": alias},
                ).mappings().first()
                if donor is not None:
                    break
            if donor is not None:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO devices (
                            device_uuid, name, ip_address, port, location, timezone,
                            active, health_status, mode, created_at
                        )
                        VALUES (
                            :uuid, :name, :ip, :port, :location, :tz,
                            TRUE, 'UNKNOWN', 'NORMAL', NOW()
                        )
                        """
                    ),
                    {
                        "uuid": str(uuid4()),
                        "name": canonical,
                        "ip": donor["ip_address"],
                        "port": donor["port"] or 4370,
                        "location": donor["location"],
                        "tz": donor["timezone"] or "UTC",
                    },
                )

    if "attendance_logs" in tables:
        for old in sorted(alias_names):
            conn.execute(
                sa.text(
                    """
                    DELETE FROM attendance_logs AS alias
                    USING attendance_logs AS keep
                    WHERE alias.device_id = :old
                      AND keep.device_id = :canonical
                      AND alias.employee_code = keep.employee_code
                      AND alias.timestamp = keep.timestamp
                    """
                ),
                {"old": old, "canonical": canonical},
            )
            conn.execute(
                sa.text(
                    "UPDATE attendance_logs SET device_id = :canonical WHERE device_id = :old"
                ),
                {"old": old, "canonical": canonical},
            )

    for table in ("device_user_mappings", "device_commands"):
        if table not in tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "device_id" not in cols:
            continue
        for old in sorted(alias_names):
            if table == "device_user_mappings":
                # Drop legacy mappings that would collide with an active canonical identity.
                conn.execute(
                    sa.text(
                        """
                        DELETE FROM device_user_mappings AS alias
                        USING device_user_mappings AS keep
                        WHERE alias.device_id = :old
                          AND keep.device_id = :canonical
                          AND alias.device_user_id = keep.device_user_id
                        """
                    ),
                    {"old": old, "canonical": canonical},
                )
            conn.execute(
                sa.text(f"UPDATE {table} SET device_id = :canonical WHERE device_id = :old"),
                {"old": old, "canonical": canonical},
            )

    if "devices" in tables:
        values_sql = _names_as_values(sorted(alias_names))
        conn.execute(
            sa.text(
                f"""
                UPDATE devices
                SET active = FALSE,
                    health_status = 'OFFLINE',
                    mode = 'OFFLINE',
                    quarantine_reason = COALESCE(
                        quarantine_reason,
                        'Merged into canonical device id'
                    )
                WHERE name IN (SELECT column1 FROM (VALUES {values_sql}) AS t)
                """
            )
        )
        if canonical_ip:
            conn.execute(
                sa.text(
                    """
                    UPDATE devices
                    SET active = FALSE,
                        health_status = 'OFFLINE',
                        mode = 'OFFLINE',
                        quarantine_reason = COALESCE(
                            quarantine_reason,
                            'Duplicate IP merged into canonical device'
                        )
                    WHERE ip_address = :ip
                      AND name <> :canonical
                      AND active IS TRUE
                    """
                ),
                {"ip": canonical_ip, "canonical": canonical},
            )
        conn.execute(
            sa.text(
                """
                UPDATE devices
                SET active = TRUE,
                    mode = CASE WHEN mode IN ('OFFLINE', 'DEGRADED') THEN 'NORMAL' ELSE mode END
                WHERE name = :name
                """
            ),
            {"name": canonical},
        )


def downgrade() -> None:
    raise NotImplementedError("Cannot split remapped attendance_logs device_id values")
