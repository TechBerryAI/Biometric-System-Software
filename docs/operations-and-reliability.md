# Operations and Reliability

## Reliability Principles

- never trust edge write success blindly
- always verify by readback
- prefer eventual consistency with reconciliation
- contain failures, do not propagate corruption
- quarantine unstable devices rather than force control

## Device Modes

- `NORMAL` - full safe operational behavior
- `READ_ONLY` - no mutation commands accepted
- `DEGRADED` - restricted operation due to risk indicators
- `QUARANTINED` - high-risk isolation, operator intervention required
- `OFFLINE` - connectivity unavailable

## Queue Safety Guarantees

- per-device lock serialization
- lock heartbeat renewal during long writes
- idempotency keys to deduplicate requests
- replay-safe execution history
- pre-retry verification recovery check
- dead-letter fallback for repeated failures

## Firmware Governance

- uncertified/unknown/unstable firmware is restricted
- compatibility and certification tracked independently
- risky operations can be blocked by operation safety profile and governance policy

## Operational Endpoints

- `/health/*` for service and subsystem checks
- `/ops/*` for metrics, audit logs, device commands, firmware profiles, and reconciliation jobs
- `/forensics/*` for correction and raw-event investigation

Global maintenance/freeze and per-device quarantine are enforced by `system_governance_service` and updated via PostgreSQL when HTTP toggles are not exposed.

## Alert Conditions to Monitor

- increasing lock contention events
- queue starvation
- verification failure spikes
- reconciliation backlog growth
- dead-letter accumulation
- quarantined device count > 0
- emergency freeze unexpectedly enabled

## Recovery Patterns

- stale command recovery worker requeues or dead-letters safely
- reconciliation jobs escalate when unresolved
- runtime risk scoring drives mode downgrades before data risk escalates
- operator approvals enforce manual gates for high-risk interventions
