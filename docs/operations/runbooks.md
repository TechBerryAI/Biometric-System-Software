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

## 6. Incident Artifacts

Capture for each incident:

- request/correlation IDs
- affected `command_uuid` values
- device mode and runtime risk level
- recent `device_sync_events`
- reconciliation and approval records
