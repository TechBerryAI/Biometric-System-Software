# Runbooks

## 1. Emergency Freeze

When to use:

- widespread verification failures
- active replay anomaly
- suspected operator error impacting multiple devices

Actions:

1. Enable emergency freeze in PostgreSQL (see `docs/api/overview.md` for SQL).
2. Confirm queue mutations are blocked via `/ops/metrics` (`emergency_freeze_active`).
3. Inspect `/ops/device-commands?status=DEAD_LETTER` and `/ops/reconciliation-jobs`.
4. Triage root cause before clearing `emergency_freeze_mode`.

## 2. Device Quarantine

When to use:

- firmware instability
- repeated protocol/timeout errors
- drift or verification failures for a single device

Actions:

1. Set device mode to `QUARANTINED` in PostgreSQL (see `docs/api/overview.md` for SQL).
2. Confirm device mode via `/health/devices` or `/ops/metrics` (`quarantined_devices`).
3. Review firmware profiles via `/ops/firmware-profiles` and certifications via `/ops/firmware-certifications`.
4. Open reconciliation and remediation ticket.

## 3. Dead Letter Recovery

1. Inspect `/ops/device-commands?status=DEAD_LETTER`.
2. Group by error type and firmware.
3. Validate firmware certification and safety profile.
4. Replay with `/ops/device-commands/{command_uuid}/process` only after cause is resolved.

## 4. Reconciliation Backlog Escalation

1. Check `/ops/reconciliation-jobs` and `/ops/metrics` (`reconciliation_pending`).
2. Prioritize `ESCALATED` and `REVIEW_REQUIRED` statuses.
3. Resolve deterministic issues first.
4. Keep unresolved high-risk jobs in manual review queue.

## 5. Firmware Introduction Procedure

1. Register firmware in certification catalog (`/ops/firmware-certifications`).
2. Start in restricted mode.
3. Validate verification success rates and drift impact.
4. Promote status only after stability evidence.

## 7. Missing evening punches / short workdays (~3h)

Symptom: In ~09:30, Out ~13:00, work ~3h even though people worked 9–10h. Corrected days look fine.

Cause: Evening punches were never stored (or were lost from the terminal buffer). First/last summary is correct on the punches that exist. Dual device labels for one IP (`Workplace Entrance` + `main-entrance`) made history harder to reason about.

Actions:

1. Confirm Alembic head includes `0019` (canonicalizes device id to `ZK_DEVICE_ID`).
2. Run **Sync now** (always pulls everything still on the terminal):
   - UI: sidebar **Sync now**
   - API: `POST /sync/device` (defaults to `full=true`)
   - CLI: `cd backend && .venv/bin/python scripts/sync_from_device.py`
3. Check incomplete days: `cd backend && .venv/bin/python scripts/report_incomplete_days.py`
   Ops metric `incomplete_attendance_days` on `/ops/metrics` counts weekday days whose last punch is before 15:00.
4. Days still short after sync: evenings are no longer on the device — use Attendance Adjust (already trusted).
5. Keep auto-sync on when the network is reliable (`DEVICE_AUTO_SYNC_ENABLED=true`), or run Sync at least once after typical exit time so evenings do not roll off the terminal before the next morning pull.
