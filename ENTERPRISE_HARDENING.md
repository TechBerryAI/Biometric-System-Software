# Enterprise Hardening - Architecture and Operations

## 1) Enterprise Architecture
- API layer is now split into functional domains: `auth`, `employees`, `attendance`, `insights`, `sync`, and `ops`.
- Security and governance are centralized in `backend/app/core/security.py` with JWT validation, password hashing, and RBAC permission guards.
- Operational side effects are decoupled from request latency through `device_commands` and background workers (`Celery`) for execution/recovery/reconciliation.
- Attendance truth remains append-only (`attendance_logs`) and session derivation remains deterministic from logs.

## 2) Identity Model
- Immutable workforce identity continues to use `employees.employee_uuid`.
- Mutable device identity remains `employees.device_user_id`, with historical lineage preserved in `device_user_mappings`.
- Human operator identity is now modeled by `users.user_uuid` with role + active state.
- Audit actor identity is captured via `audit_logs.actor_user_uuid`.

## 3) Queue and Reconciliation Architecture
- Employee write APIs enqueue `UPSERT_USER` commands into `device_commands`; frontend is never blocked on hardware writes.
- Command lifecycle now includes `PENDING -> RUNNING -> VERIFYING -> SUCCESS|FAILED|RETRYING|DEAD_LETTER|RECONCILIATION_REQUIRED`.
- `process_device_commands` uses per-device Redis lock serialization + idempotency keys + retry backoff metadata.
- `verification_results` stores readback validation (`expected_state`, `actual_state`, `mismatch_details`) for every processed write.
- Verification failures never assume success; commands are failed and `reconciliation_jobs` are generated for operator follow-up.
- `reconcile_devices` compares active mappings vs live device users and emits drift telemetry to `device_sync_events`.
- `recover_stale_commands` reclaims stale `RUNNING`/`VERIFYING` rows using heartbeat timestamps.
- `command_execution_history` tracks every attempt with worker id, execution hash, verification outcome, and terminal status for replay safety.
- Replay handling now performs pre-retry readback verification to recover commands that succeeded before worker crash/timeout.
- Per-device lock contention is emitted as first-class telemetry (`LOCK_CONTENTION`) and retried with bounded backoff.

## 4) Security Model
- JWT access tokens + refresh tokens with rotation are implemented in `auth` APIs.
- Passwords are hashed with bcrypt (`passlib`), never stored in plaintext.
- Login throttle hooks are enforced through Redis-backed counters.
- API boundaries are now role/permission guarded using FastAPI dependencies.
- Request correlation IDs are propagated per request (`x-request-id`) for traceability.

## 5) RBAC Matrix
- `SUPER_ADMIN`: full platform privileges.
- `HR_ADMIN`: employee management, sync triggers, reports, anomaly operations.
- `MANAGER`: reports, AI operations, anomaly operations.
- `VIEWER`: report/read-only analytics.
- `DEVICE_OPERATOR`: device/queue/sync and metrics operations.

## 6) Device Orchestration
- Default device registry is maintained in `devices` with health status and last_seen.
- Command execution uses lock-based per-device serialization (Redis lock) to reduce conflicting concurrent hardware access.
- Health checks and reconciliation emit `device_sync_events` for operational diagnostics.
- Firmware fingerprinting is captured during health checks and queued writes (`firmware_profile` on commands).
- `device_firmware_profiles` defines per-firmware write capabilities and safe strategy metadata.
- Global `DEVICE_READ_ONLY=true` disables all device mutations at API + queue processor layers.
- `device_state_snapshots` captures periodic and pre/post mutation snapshots for drift forensics and incident recovery.
- Distributed lock heartbeat renewal keeps long-running writes serialized while allowing stale lock recovery on worker death.
- Device modes now support `NORMAL`, `READ_ONLY`, `DEGRADED`, `QUARANTINED`, and `OFFLINE` for runtime containment.
- Runtime risk scoring (`device_runtime_health`) drives automatic degraded/quarantine transitions on instability spikes.

## 7) Firmware Certification System
- `certified_firmware_profiles` is the canonical production certification matrix.
- Unknown/uncertified/unstable firmware is auto-restricted: queued writes are blocked and device mode is moved to `READ_ONLY`.
- Certification records include stability score, known bugs, safe rollout recommendations, and verification strategy guidance.
- `POST /ops/firmware-certifications` supports controlled certification updates by privileged operators.

## 8) AI Governance
- AI remains advisory/analytical and cannot mutate attendance truth.
- Per-user AI rate limits + daily quota enforcement are added via Redis governance keys.
- Existing provider abstraction is preserved; governance wraps endpoint access and usage control.

## 9) Deployment Recommendations
- Use strong production `JWT_SECRET_KEY`, rotate periodically, and isolate per environment.
- Run at least one dedicated Celery worker for `process_device_commands` + reconciliation tasks.
- Enforce network policy and TLS between API, Redis, DB, and workers.
- Pin Redis persistence and DB backups for audit/compliance retention.

## 10) Scaling Limitations
- Current device IO implementation still targets one configured hardware endpoint (`ZK_DEVICE_ID`) at runtime; registry is ready but active polling is single-source.
- Large frontend bundles need additional code splitting.
- AI quotas are Redis-key based; very high multi-tenant scale should move quotas and cost accounting to durable analytics storage.
- Regional queue partitioning and worker affinity are modeled operationally through per-device serialization; true multi-region broker sharding remains a deployment concern.

## 11) Operational Runbooks
- Bootstrap admin: call `POST /auth/bootstrap-admin` once after setting bootstrap env vars.
- Incident triage: inspect `/ops/metrics`, `/ops/device-commands`, and `/ops/audit-logs`.
- Queue stuck: run stale recovery task and investigate dead-letter commands with correlation IDs.
- Sync drift: inspect latest `RECONCILIATION` events and compare mapping/device user deltas.
- Replay anomaly: inspect `/operations/queue` for `replay_recovered_success` and correlate with `command_execution_history`.
- Firmware mismatch: inspect `/operations/firmware-health` for devices missing a safety profile.
- Dead letters: inspect `/operations/dead-letters`, resolve cause, then replay via controlled requeue after policy verification.
- Governance freeze: use `/governance/emergency-freeze` for immediate fleet mutation halt.
- Maintenance windows: use `/governance/maintenance` to pause all write pipelines safely.
- Device quarantine: use `/governance/quarantine` when firmware/runtime instability requires hard isolation.
- Approval workflows: use `/governance/approvals/request` and `/governance/approvals/{approval_uuid}` for auditable high-risk action acknowledgment.

## 12) Disaster Recovery Assumptions
- Attendance truth is recoverable from `attendance_logs`; `attendance_sessions` can be deterministically rebuilt.
- Queue recovery assumes durable DB storage for `device_commands`.
- Audit continuity assumes PostgreSQL backups include `audit_logs` without pruning.
- Replay continuity assumes `command_execution_history` retention window overlaps expected incident investigation time.

## 13) Firmware Compatibility Caveats
- Queue retries are bounded and backoff-based, but pyzk behavior can vary across firmware.
- Unsupported or vendor-specific write paths are isolated through command allowlists and explicit rejection auditing.
- New command types should be added only behind explicit compatibility checks + readback verification handlers.
- Existing safety policy intentionally does not allow destructive pyzk operations (clear/delete/restart/poweroff paths are blocked by design).
- pyzk transport remains semi-trusted; `PyZKAdapter` enforces bounded reconnect retries and defensive error handling.

## 14) Storage, Retention, and Fleet Governance
- `apply_retention_policies` worker prunes snapshots, execution history, old reconciliation rows, and fleet metrics based on retention env settings.
- `aggregate_fleet_health` captures global queue pressure, risk distribution, and backlog health for operations center reporting.
- `seed_firmware_certifications` guarantees baseline `unknown` firmware policy coverage.

## 15) Chaos and Failure Validation
- Baseline test suite now includes replay-hash determinism, snapshot hash determinism, and runtime risk-scoring checks.
- pyzk simulator scaffolding exists under `backend/tests/mocks/pyzk_simulator.py` for failure-injection scenarios.
- Recommended pre-prod chaos matrix:
  - worker termination during `VERIFYING`
  - Redis lock churn / broker restart
  - repeated pyzk timeouts and malformed responses
  - prolonged firmware readback mismatch
  - reconciliation backlog escalation

## 16) Production Hardening Checklist
- [ ] Rotate JWT secret and set secure env values in deployment platform.
- [ ] Seed bootstrap admin and remove bootstrap password after first use.
- [ ] Enforce HTTPS and secure cookie policy if refresh tokens are moved to cookies.
- [ ] Monitor dead-letter count and reconciliation drift alarms.
- [ ] Add immutable storage policy for audit logs and backup validation jobs.
- [ ] Add automated API/RBAC/queue integration tests in CI for all privileged flows.
- [ ] Monitor `/operations/device-drift` and reconcile snapshot-hash changes against expected HR updates.
- [ ] Set conservative defaults for UID/privilege/card rewrite policy env flags (all false by default).
- [ ] Validate Celery beat includes `capture_device_snapshot` and stale reconciliation escalation workers.
