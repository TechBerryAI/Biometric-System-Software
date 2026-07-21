# Testing Strategy — Biometric System Software

**Status:** Canonical  
**Scope:** Backend (FastAPI/Celery) + Frontend (React/Vite)  
**Schema baseline:** Post-migration `0018` (simplified attendance; no forensics/approval ledger tables)

## 1. Goals

1. Detect **any regression** in existing product behavior on every code change.
2. Cover **every real** HTTP route, ORM model, service, Celery task, frontend page, API client export, AI module, and biometric workflow with at least one automated test (see [TRACEABILITY_MATRIX.md](./TRACEABILITY_MATRIX.md)).
3. Prefer fast, deterministic unit tests; escalate to Postgres + device-simulator integration and Playwright E2E for workflows that cannot be trusted at unit level alone.
4. Never claim coverage for modules that are **not implemented**.

## 2. Layers

| Layer | Location | Speed | Depends on |
|-------|----------|-------|------------|
| Backend unit | `backend/tests/unit/` | <1s each | Mocks / pure functions / simulator |
| Backend API | `backend/tests/api/` | Fast | TestClient + transactional DB (or overridden deps) |
| Backend integration | `backend/tests/integration/` | Medium | Postgres + SimulatedPyZK |
| Backend workers | `backend/tests/workers/` | Medium | Celery eager / direct task bodies |
| Backend scenario | `backend/tests/e2e_scenarios/` | Medium–slow | Full backend path, no browser |
| Frontend unit | `frontend/src/**/*.test.{ts,tsx}` | Fast | Vitest + RTL + MSW |
| Browser E2E | `e2e/scenarios/` | Slow | Playwright against local UI (`make test-e2e`) |

### Failure-detection philosophy

- Unit/API fail in seconds → primary author feedback loop.
- Integration/workers catch device queue, locks, governance, sync idempotency.
- E2E catches permission UX, navigation, exports, multi-page company workflows.
- Flaky tests are quarantined with an issue tag; never silently skipped without documentation.

## 3. Tooling

| Concern | Choice |
|---------|--------|
| Backend runner | `pytest` + `pytest-cov` + `pytest-asyncio` |
| API client | FastAPI `TestClient` / `httpx` |
| Device I/O in CI | `backend/tests/mocks/pyzk_simulator.py` — **never** a live F22 |
| Redis | Mocked Redis clients in unit/integration |
| Celery | `task_always_eager` or invoke task bodies directly |
| Frontend | Vitest + React Testing Library + jsdom + MSW |
| Browser E2E | Playwright against local UI (`make test-e2e`) |
| Coverage gate | Backend `app/` line ≥ 85%; critical routes/tasks = 100% mapped in matrix |
| Commands | Repo-root `Makefile` (`make test`, `make test-unit`, …) |

## 4. Repository layout

```text
docs/testing/
  TESTING_STRATEGY.md
  TRACEABILITY_MATRIX.md
backend/
  requirements.txt          # runtime + test deps (single file)
  tests/
    conftest.py
    factories.py
    mocks/pyzk_simulator.py
    unit/ api/ integration/ workers/ e2e_scenarios/
frontend/
  vitest.config.ts
  src/test/setup.ts
  src/**/*.test.ts(x)
e2e/
  playwright.config.ts
  scenarios/
scripts/check_traceability_matrix.py
.github/workflows/ci.yml
Makefile
```

## 5. Naming and test IDs

Stable IDs appear in test markers and the matrix:

| Prefix | Meaning |
|--------|---------|
| `BE-UNIT-…` | Backend unit |
| `BE-API-…` | Backend HTTP API |
| `BE-INT-…` | Backend integration |
| `BE-WRK-…` | Celery / workers |
| `BE-SCN-…` | Backend multi-step scenario |
| `FE-UNIT-…` | Frontend unit/component |
| `E2E-…` | Playwright |

Example: `@pytest.mark.testid("BE-API-AUTH-002")`

## 6. Workflows and business rules (must pass)

### 6.1 Authentication and authorization

| Rule | Expected | Negative |
|------|----------|----------|
| Bootstrap admin | Creates first SUPER_ADMIN when none exists | Rejected when admin already exists |
| Login | Returns access + refresh tokens | Wrong password / inactive user / rate-limit lockout |
| Refresh | Rotates refresh token | Reuse of revoked/rotated token fails |
| Logout | Revokes refresh | Subsequent refresh fails |
| Password change | Issues new tokens; old refresh invalid | Wrong current password |
| RBAC | `require_permissions` enforces `ROLE_PERMISSIONS` | Missing permission → 403 |
| Operator capabilities | `account_flags` unlock adjust + forensic_audit UI | Non-operator cannot POST `/attendance/adjust/correct` |

### 6.2 User management

| Rule | Expected | Negative |
|------|----------|----------|
| Create user | SUPER_ADMIN / IT with `user:manage` | Forbidden roles / duplicate email |
| Profile update | Own name update | Unauthenticated |

### 6.3 Employee management

| Rule | Expected | Negative |
|------|----------|----------|
| List/get | Active employees and detail | Cross-tenant N/A (single org) |
| Upsert metadata | Creates/updates employee; may enqueue UPSERT_USER | Writes blocked under governance / `DEVICE_WRITES_ENABLED=false` |
| Identity change | Name change → mapping rollover + UPSERT; department/shift-only stay DB | Collision on device_user_id |
| Offboard | Soft-deactivate + DELETE_USER queue | Already departed |

### 6.4 Departments and shifts (fields only)

| Rule | Expected | Negative |
|------|----------|----------|
| Department | Stored on `Employee.department`; UI presets + Other | Empty Other without custom name fails client validation |
| Shift | `shift_start` / `shift_end` strings on employee | Not synced to terminal memory |

### 6.5 Attendance ingest and punch processing

| Rule | Expected | Negative |
|------|----------|----------|
| Sync | Fetch users + attendance → idempotent `attendance_logs` | Device unreachable → error, no partial silent success |
| Dedup | Noisy duplicate punches pruned / not double-inserted | Identical punches within window ignored |
| Punch types | `classify_punch` / `resolve_punch_types_for_day` | Legacy fingerprint repaired |
| Sessions | Rebuild from logs (pairing check-in/out) | Missing checkout → open session rules |

### 6.6 Device synchronization and F22 / memory updates

| Rule | Expected | Negative |
|------|----------|----------|
| UPSERT_USER | Write + readback verify → SUCCESS | Verify fail → RETRYING / DEAD_LETTER |
| DELETE_USER | Delete + verify gone | Lock contention |
| Attlog Tier A | Selective edit + verify | Unsupported firmware → Tier C / error |
| Attlog Tier B | Rewrite path gated by policy | Clear-all blocked unless allowed |
| Offline resync | After probe recovery, sync catches up | Continues failing while OFFLINE |

### 6.7 Attendance corrections (manual / operator)

| Rule | Expected | Negative |
|------|----------|----------|
| Preview day | Returns punches for local date | Unknown employee |
| Apply | Prefer verified device write; else DB-only path | Non-operator 403; day lock contention |
| Finalize | On SUCCESS replace day logs + rebuild sessions | FAILED marks correction failed |

### 6.8 Device command queue / replay / races

| Rule | Expected | Negative |
|------|----------|----------|
| Enqueue | Idempotency key; allowlisted types only | Unknown type rejected |
| Claim | Serialize per device; CORRECT_ATTENDANCE prioritized | Two workers cannot claim same cmd |
| Stale recovery | RUNNING past heartbeat → RETRYING/DEAD_LETTER | Healthy heartbeat left alone |
| Manual process | `POST /ops/device-commands/{uuid}/process` | Non-`device:manage` 403 |

### 6.9 Governance

| Rule | Expected | Negative |
|------|----------|----------|
| Maintenance / emergency freeze | Blocks device writes | Enqueue/process fail closed |
| Device mode READ_ONLY / QUARANTINED / OFFLINE | Blocks writes | Reads may continue |

### 6.10 Reports and exports

| Rule | Expected | Negative |
|------|----------|----------|
| Daily summary APIs | Correct aggregates for date/range | Empty day → empty/absent rows |
| Excel/PDF/Word | Client generates downloadable blobs | Invalid empty payload handled |

### 6.11 AI insights (advisory only)

| Rule | Expected | Negative |
|------|----------|----------|
| Management insights | Returns structured bullets; cacheable | Missing API key → degrade, no crash |
| Anomalies | Heuristic + optional LLM explain | Must **not** mutate attendance tables |
| Overtime heuristic | `overtime_spike` anomaly key when rates high | Not a payroll engine |

### 6.12 Health and ops observability

| Rule | Expected | Negative |
|------|----------|----------|
| `/health` | Public liveness | — |
| `/health/db|redis|devices|ai|queue|reconciliation` | Authenticated metrics-read | 401/403 without permission |

### 6.13 Frontend UX rules

| Rule | Expected | Negative |
|------|----------|----------|
| Route guards | Permission / capability redirects | Unauthenticated → `/login` |
| Nav | Sidebar only shows permitted items | Empty roles see minimal nav |
| Sync button | Triggers `POST /sync/device` + query invalidation | Surfaces API error message |
| Notification bell | Presentational stub only | No API call expected |

## 7. Scenario-based E2E (company operations day)

Simulate real operations (browser E2E + backend scenario):

1. Bootstrap / login as admin  
2. Create HR account  
3. Onboard employees (department + shift fields)  
4. Device sync (simulator) populates punches  
5. View attendance / daily summary  
6. Operator applies attendance correction  
7. Ops reprocess / audit command history  
8. Dashboard AI insights (mocked provider)  
9. Export report (Excel/PDF/Word)  
10. Offboard employee + device delete command  

**Omitted by design:** payroll generation, leave approvals, holiday calendars (not implemented).

## 8. Out of scope / not implemented

Do **not** write tests that invent these features:

| Topic | Status |
|-------|--------|
| Holiday management | Not implemented |
| Leave / PTO module | Not implemented |
| Payroll calculations | Not implemented |
| Late arrival / early exit engines | Not implemented (no comparison to shift times) |
| Approval workflows | Removed in migration `0018` |
| Notifications (push/email/in-app feed) | Bell UI stub only |
| AI correction time suggestions | Not implemented (insights/anomalies only) |
| External vendor / ERP sync | Not implemented (device sync only) |
| Dedicated Department / Shift CRUD APIs | Fields only |

When product ships any of the above, add matrix rows as `UNIMPLEMENTED → cover on ship`.

## 9. How to run

```bash
make help
make install              # backend/.venv + frontend npm + Playwright

make test                 # backend + frontend + matrix + e2e list
make test-backend         # all backend pytest
make test-unit            # unit only
make test-api             # API only
make test-integration
make test-workers
make test-scenarios
make test-backend-cov
make test-frontend
make test-e2e             # Playwright (skips if UI unreachable)
make test-e2e-list
make test-matrix
```

## 10. CI gates

PRs fail if any of:

1. Backend unit/API/integration/worker tests fail  
2. Frontend unit tests fail  
3. Playwright scenario list / E2E failures when UI is available  
4. Coverage below thresholds  
5. `make test-matrix` finds an unmapped route, Celery task, or frontend page  

## 11. Device simulation policy

- CI and local default: `SimulatedPyZKDevice` only.  
- Hardware smoke against a real F22 is **manual** / optional staging — not a CI merge gate.  
- Fault injection: timeout/OSError via simulator `fail_rate` for offline and retry paths.
