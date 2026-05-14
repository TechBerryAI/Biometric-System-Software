# Runbooks

## 1. Emergency Freeze

When to use:

- widespread verification failures
- active replay anomaly
- suspected operator error impacting multiple devices

Actions:

1. Call `/governance/emergency-freeze` with reason.
2. Confirm queue mutations are blocked.
3. Inspect `/operations/alerts` and `/operations/incident-timeline`.
4. Triage root cause before unfreezing.

## 2. Device Quarantine

When to use:

- firmware instability
- repeated protocol/timeout errors
- drift or verification failures for a single device

Actions:

1. Call `/governance/quarantine`.
2. Confirm device mode is `QUARANTINED`.
3. Review runtime and firmware status in `/operations/fleet-health` and `/operations/firmware-health`.
4. Open reconciliation and remediation ticket.

## 3. Dead Letter Recovery

1. Inspect `/operations/dead-letters`.
2. Group by error type and firmware.
3. Validate firmware certification and safety profile.
4. Only replay after cause is resolved and verification policy is intact.

## 4. Reconciliation Backlog Escalation

1. Check `/operations/reconciliation`.
2. Prioritize `ESCALATED` and `REVIEW_REQUIRED`.
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
