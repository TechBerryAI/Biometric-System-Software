"""Aggregate operational metrics from device_sync_state rows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.devices.models.device_sync_state import DeviceSyncState


def _drift_total(drift_counts: dict | None) -> int:
    if not drift_counts:
        return 0
    return int(drift_counts.get("missing_on_device", 0)) + int(drift_counts.get("missing_mapping", 0))


def _lock_contention(conflict_resolution: dict | None) -> int:
    if not conflict_resolution:
        return 0
    return int(conflict_resolution.get("lock_contention", 0))


def count_reconciliation_pending(db: Session) -> int:
    """Devices with user/mapping drift awaiting reconciliation."""
    rows = db.execute(select(DeviceSyncState)).scalars().all()
    return sum(1 for row in rows if _drift_total(row.drift_counts) > 0)


def count_reconciliation_completed(db: Session) -> int:
    """Devices that have synced at least once with no outstanding drift."""
    rows = db.execute(select(DeviceSyncState)).scalars().all()
    return sum(1 for row in rows if row.sync_generation > 0 and _drift_total(row.drift_counts) == 0)


def sum_sync_drift_events(db: Session) -> int:
    """Total drift events across the fleet (missing device users + missing mappings)."""
    rows = db.execute(select(DeviceSyncState)).scalars().all()
    return sum(_drift_total(row.drift_counts) for row in rows)


def sum_lock_contention_events(db: Session) -> int:
    """Total lock contention events recorded in conflict_resolution payloads."""
    rows = db.execute(select(DeviceSyncState)).scalars().all()
    return sum(_lock_contention(row.conflict_resolution) for row in rows)
