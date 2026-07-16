"""Unit tests for device_sync_state operational metrics."""

from __future__ import annotations

from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.ops.services.sync_state_metrics import (
    count_reconciliation_completed,
    count_reconciliation_pending,
    sum_lock_contention_events,
    sum_sync_drift_events,
)


def test_sync_state_metrics_from_drift_counts(db_session) -> None:
    db_session.add(
        DeviceSyncState(
            device_id="dev-a",
            sync_generation=2,
            drift_counts={"missing_on_device": 1, "missing_mapping": 0},
            conflict_resolution={"lock_contention": 3},
        )
    )
    db_session.add(
        DeviceSyncState(
            device_id="dev-b",
            sync_generation=1,
            drift_counts={"missing_on_device": 0, "missing_mapping": 0},
            conflict_resolution={"lock_contention": 1},
        )
    )
    db_session.commit()

    assert count_reconciliation_pending(db_session) == 1
    assert count_reconciliation_completed(db_session) == 1
    assert sum_sync_drift_events(db_session) == 1
    assert sum_lock_contention_events(db_session) == 4
