# Project Structure Snapshot (for LLM planning)

> **Purpose:** Paste this file into any LLM session to reason about structure, boundaries, and how to make the repo clearer / more premium — without assuming stale product docs are still true.
>
> **Freshness:** Captures the repo as of post-migration `0018` (schema simplification). Prefer this over older claims in root `README.md` and other `docs/*.md` when they conflict.
>
> **How to use:** Attach this file and ask for structural redesign options, target folder layouts, migration steps, or “what mess to clean first.” Suggested prompts are at the end.

---

## 1. What this product actually is

**Biometric Workforce Intelligence Platform** — attendance + device operations around ZKTeco/ESSL fingerprint/card terminals.

| Is | Is not |
|----|--------|
| Pulls punch/attendance logs from physical devices via `pyzk` | A biometric template / enrollment / matching engine |
| Queues **user metadata** writes to devices (`UPSERT_USER` / `DELETE_USER`) with lock + readback | Soft that stores or deletes fingerprint templates |
| Append-only attendance logs → derived sessions | Source of truth living only on the device |
| RBAC React “operations center” for HR/IT/admin | Consumer mobile attendance app |

**Safety constraint (hard):** biometric templates stay on the device; the platform must not perform destructive template operations.

---

## 2. Tech stack (current)

| Layer | Stack |
|--------|--------|
| Frontend | React 18, TypeScript, Vite 5, React Router 6, TanStack Query, Zustand, Tailwind 3, Radix UI, Axios, Recharts, Vitest + MSW |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, Celery + Redis, JWT/bcrypt |
| Device I/O | `pyzk` (wrapped; dangerous methods blocked) |
| AI (optional) | xAI Grok — advisory insights only (`XAI_API_KEY`) |
| Data | PostgreSQL (canonical), Redis (Celery + locks), SQLite in-memory for tests |
| E2E / CI | Playwright (`e2e/`), GitHub Actions (`.github/workflows/ci.yml`), Makefile |
| Bootstrap | `make install` + `make start` locally; `make start-vm` on the VM |

---

## 3. Top-level layout

```text
Biometric-System-Software/
├── README.md
├── Makefile                  # install / test targets
├── package.json              # npm workspaces root + Playwright
├── scripts/                  # start-vm.js, traceability check
├── .github/workflows/ci.yml
├── backend/                  # FastAPI app + Alembic + pytest
├── frontend/                 # Vite React app (workspace package)
├── docs/                     # architecture / api / operations / testing
└── e2e/                      # Playwright scenarios
```

**Entry points**

| Goal | Command |
|------|---------|
| Full stack (local) | `make start` (API `:8000`, UI `:5173`, Celery when Redis is up) |
| Full stack (VM) | `make start-vm` / `npm run start:vm` |
| Backend | `uvicorn app.main:app` from `backend/` |
| Frontend | `npm run dev` from repo root (workspace) |
| Tests | `make test` / `make test-backend` / `make test-frontend` / `make test-e2e` |

---

## 4. Backend structure

```text
backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, request-id, /health*
│   ├── api/                    # Thin HTTP routers
│   │   ├── auth.py
│   │   ├── employee.py         # ~16k — heaviest router
│   │   ├── attendance.py
│   │   ├── attendance_correction.py
│   │   ├── sync.py             # POST /sync/device
│   │   ├── operations.py       # /ops/device-commands, /ops/metrics
│   │   └── insights.py         # /insights/*
│   ├── core/
│   │   ├── config.py           # pydantic-settings (.env)
│   │   ├── database.py
│   │   ├── security.py         # JWT + RBAC Permission/roles
│   │   ├── operator_access.py
│   │   ├── device_policy.py    # write flags / attlog tiers (code, not env)
│   │   └── redis_keys.py
│   ├── models/                 # 9 ORM entities (see §4.2)
│   ├── schemas/                # Pydantic I/O
│   ├── services/               # Business + device orchestration (largest surface)
│   ├── workers/
│   │   ├── celery_app.py       # beat schedule
│   │   └── tasks.py
│   ├── ai/                     # Grok provider, insights, anomaly, cache
│   └── constants/
│       └── keep_list.py        # Site-specific employee keep roster (smell)
├── alembic/versions/           # 0015→0018 (files dated 20260713/14)
├── tests/                      # unit / api / integration / workers / e2e_scenarios
├── scripts/                    # ops one-offs (purge, probe, grant access, SQL setup)
├── requirements.txt
└── .env.example
```

### 4.1 Live API domains

| Prefix | Role |
|--------|------|
| `/auth` | bootstrap, login, refresh, logout, me, password, user create |
| `/employees` | CRUD, soft offboard, daily attendance |
| `/attendance` | logs, sessions, daily summary |
| `/attendance/adjust` | correction capabilities / preview / apply |
| `/sync` | manual device sync |
| `/ops` | device command queue + operational metrics |
| `/insights` | management + anomaly insights |
| `/health*` | liveness + dependency probes |

**Removed / gone after schema `0018` (docs may still mention):** dedicated forensics HTTP, firmware certification routes, reconciliation-job tables, audit-log / correction-overlay / verification-history tables. Treat those as **historical**, not current architecture.

### 4.2 ORM models (canonical)

`User`, `RefreshToken`, `Employee`, `Device`, `DeviceUserMapping`, `DeviceCommand`, `AttendanceLog`, `AttendanceSession`, `SystemControlState`

Truth model: **`attendance_logs` append-only** → `attendance_sessions` derived/rebuildable. Device writes durable in **`device_commands`** (PostgreSQL) with Celery draining the queue.

### 4.3 Services inventory (size ≈ complexity)

| File | ~LOC | Role |
|------|------|------|
| `device_command_service.py` | 773 | Queue claim / process / verify |
| `attendance_correction_service.py` | 573 | DB (+ optional attlog) corrections |
| `device_service.py` | 486 | pyzk user/attendance I/O |
| `attendance_helpers.py` | 461 | session/rebuild helpers |
| `employee_offboard_service.py` | 434 | soft-delete + DELETE_USER |
| `attendance_service.py` | 433 | pull + session rebuild |
| `device_attlog_protocol.py` | 230 | attlog edit tiers |
| `auth_service.py` | 204 | login/bootstrap |
| others | smaller | locks, registry, punch classification, governance, Grok context, codec, adapter |

**Intended layering:** `api` (thin) → `services` (domain) → `models` / `pyzk_adapter` / Redis / DB. Workers call services on a schedule.

### 4.4 Celery beat (when Redis up)

- `process_device_commands` ~15s  
- `recover_stale_commands` ~60s  
- `reconcile_devices` on configured interval  
- Optional auto sync / connectivity probe if `DEVICE_AUTO_SYNC_ENABLED`

---

## 5. Frontend structure

```text
frontend/src/
├── main.tsx                    # Query → Router → Auth → App
├── App.tsx                     # Routes + capability gates
├── auth/                       # AuthContext, RequireAuth, permissions, sessionCapabilities
├── pages/                      # Route screens (largest files live here)
│   ├── Login.tsx
│   ├── Dashboard.tsx           # ~71k — God page smell
│   ├── Employees.tsx
│   ├── EmployeeProfile.tsx
│   ├── Attendance.tsx
│   ├── Reports.tsx
│   ├── Operations.tsx
│   ├── Settings.tsx
│   ├── Profile.tsx
│   └── Audit.tsx               # aliases: /corrections, /raw-attendance, /forensics, /device-history → /audit
├── components/
│   ├── layout/                 # AppLayout, Sidebar, TopBar
│   ├── ui/                     # Radix/shadcn-style primitives
│   ├── dashboard/, employees/, attendance/, accounts/, reports/, settings/
├── services/api.ts             # ~500 LOC — single Axios client + all domain API methods
├── hooks/                      # dashboard / trend / recent logs
├── stores/ui-store.ts          # Zustand UI
├── providers/query-provider.tsx
├── config/api.ts               # VITE_API_URL (default `/api`)
├── lib/                        # cn, dates, dashboardAnalytics
├── utils/reportExports/        # Excel / PDF / Word
├── types/
└── test/                       # Vitest setup + MSW
```

### 5.1 State & auth patterns

- **Server state:** TanStack Query + `services/api.ts`
- **Session:** React context + JWT access/refresh interceptors
- **UI chrome:** Zustand
- **Authorization:** dual systems — string permissions (`employee:view`) **and** session capabilities (`forensic_audit`, `attendance_adjust`)

### 5.2 Routes (capability-gated)

| Route | Gate (approx) |
|-------|----------------|
| `/login` | public |
| `/` | home by capability |
| `/employees`, `/employees/:id` | `employee:view` |
| `/attendance` | `reports:read` |
| `/reports` | `reports:read` |
| `/operations` | `device:manage` |
| `/settings` | `metrics:read` |
| `/audit` | `forensic_audit` |

---

## 6. Cross-cutting concerns map

```text
                    ┌─────────────┐
                    │  React UI   │
                    │  (Vite)     │
                    └──────┬──────┘
                           │ /api → FastAPI
                    ┌──────▼──────┐
                    │  API routers│
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Auth/RBAC    Domain services   Insights/AI
              │            │
              │     ┌──────┴──────┐
              │     ▼             ▼
              │  PostgreSQL    Device queue
              │  (truth)     (device_commands)
              │                   │
              │            ┌──────▼──────┐
              │            │ Celery+Redis │
              │            └──────┬──────┘
              │                   ▼
              │            pyzk → ZK/ESSL terminal
              │            (metadata + attlog only)
              └───────────────────────────────
```

| Concern | Where it lives |
|---------|----------------|
| Auth | `core/security`, `services/auth_service`, FE `auth/` |
| RBAC | Backend roles/permissions; FE `permissions` + `sessionCapabilities` |
| Device write safety | `pyzk_adapter`, `device_policy`, command verify/readback |
| Attendance truth | logs → sessions rebuild |
| Corrections | `attendance_correction_service` + attlog tiers |
| Governance | `SystemControlState`, `Device.mode` |
| Ops UI | `/operations`, Audit page |
| AI | `app/ai/*` isolated; non-mutating |

---

## 7. Structure smells & mess signals (planning targets)

Use these as the backlog for “make it premium,” not as moral judgments.

### Repo / docs

1. **Docs drift** — Root README and several `docs/*` still describe firmware certification, forensics APIs, reconciliation job tables removed in migration `0018`. Metrics stubs returning `0` reinforce the narrative gap.
2. **VM vs local bootstrap** — VM uses `start-vm.js`; local uses Makefile + separate processes.
3. **Bootstrap split** — VM uses `start-vm.js`; local uses `make start`.
4. **Dual npm lockfiles** — root (Playwright) + `frontend/` — workable but easy to confuse.
5. **Site-specific ops in product tree** — `constants/keep_list.py`, `backend/scripts/purge_departed_employees.py`.

### Backend

6. **Flat `services/` god folder** — device, attendance, auth, offboard, attlog all peers; largest module `device_command_service.py` (~773 LOC).
7. **Fat API module** — `employee.py` ~16k.
8. **Empty RBAC roles** — `MANAGER`, `VIEWER`, `DEVICE_OPERATOR` exist with empty permission sets.
9. **Multi-device model vs single-device config** — ORM supports fleet; env centers on one `ZK_DEVICE_*`.
10. **Alembic naming vs revision IDs** — dated filenames vs `0015`–`0018` revision ids (squash leftover).

### Frontend

11. **God page** — `Dashboard.tsx` ~71k lines.
12. **God API client** — single `services/api.ts` ~500 LOC for all domains.
13. **Dual authz model** — permissions strings vs capabilities (cognitive overhead).
14. **Route alias clutter** — multiple historical paths redirect to `/audit`.
15. **Components by feature folder, but pages still monolithic** — feature folders under `components/` are thin compared to page files.

### Hygiene

16. Generated artifacts smell if ever committed: `e2e/playwright-report/`, `*.tsbuildinfo`, caches.

---

## 8. What already looks solid (don’t break)

- Clear monorepo split: `backend/` · `frontend/` · `docs/` · `e2e/`
- Conventional FastAPI package: `api` / `core` / `models` / `schemas` / `services` / `workers`
- Device adapter isolation (`pyzk_adapter`) and explicit “no templates” safety stance
- Durable command queue in Postgres + Celery drain
- Append-only attendance truth with rebuildable sessions
- AI kept under `app/ai/` and marked advisory
- Test pyramid presence: pytest layers + Vitest/MSW + Playwright + CI matrix
- Traceability tooling: `docs/testing/TRACEABILITY_MATRIX.md` + `scripts/check_traceability_matrix.py`

---

## 9. Ideal design axes (for collaborative decisions)

When planning a “premium” structure, decide explicitly along these axes:

| Axis | Current | Options to discuss |
|------|---------|-------------------|
| Backend domain split | Flat `services/` | `domains/{attendance,device,identity,auth,ops}/` with api·service·model per domain |
| FE feature modules | Pages monolith + thin components | Feature folders (`features/attendance/{api,hooks,components,pages}`) |
| API client | Single `api.ts` | Per-domain clients or OpenAPI-generated SDK |
| Bootstrap | `make start` / `make start-vm` |
| Docs as SoT | Partly stale | Single current architecture snapshot (this file) + slim narrative docs |
| Multi-device | Model yes / config mostly single | First-class fleet config vs intentional single-device product |
| Authz | Permissions + capabilities | Unify into one capability/permission model |
| Ops scripts | Inside `backend/scripts` + constants | `ops/` or private tooling repo / tagged “site-local” |
| Deploy story | `make start-vm` + nginx snippets in `docs/operations/deployment.md` | Keep script-based deploy; no container manifests |

**Non-goals unless requested:** rewriting pyzk protocol, adding biometric template storage, restoring dropped forensics tables without a product decision.

---

## 10. Suggested LLM planning prompts

Copy one of these with this file attached:

1. **Structure review**  
   *“Using only this snapshot, critique the current folder layout. Propose a target architecture for a premium, maintainable monorepo. Rank improvements by impact vs migration cost.”*

2. **Backend domain reorg**  
   *“Design a domain-driven folder layout for `backend/app` that splits device queue, attendance, employees, auth, and ops without changing runtime behavior. Include a phased migration plan.”*

3. **Frontend feature modules**  
   *“Propose a feature-based frontend structure that shrinks `Dashboard.tsx` and `services/api.ts`. Show before/after tree and import rules.”*

4. **Docs & narrative cleanup**  
   *“List every claim in older docs that this snapshot contradicts. Draft a short accurate README + docs hub outline for the post-0018 product.”*

5. **DX premium pack**  
   *“Propose Docker Compose + unified start story + CI layout that matches this stack, keeping Celery/Redis/Postgres first-class.”*

6. **Bounded refactor**  
   *“Pick the single highest-ROI structural change we can finish in one PR without rewriting device protocol. Spec the PR.”*

---

## 11. Related docs (context only — verify against this snapshot)

| Doc | Note |
|-----|------|
| `docs/architecture/overview.md` | May overstate post-0018 persistence/features |
| `docs/architecture/backend.md` | Stale on forensics/firmware/reconciliation tables |
| `docs/architecture/frontend.md` | Mostly still useful |
| `docs/api/overview.md` | Mentions removed routes |
| `docs/testing/*` | Closer to current simplified schema |
| Root `README.md` | Marketing language ahead of slimmed schema |

**Rule for LLMs:** If another doc conflicts with this file, prefer this file for structure decisions until docs are resynced.

---

## 12. Quick “current truth” checklist

- [ ] Templates never leave / never deleted by this software  
- [ ] Attendance truth = append-only logs in Postgres  
- [ ] Device metadata writes = queued `device_commands` + verify  
- [ ] No Docker in repo today  
- [ ] Schema simplified in Alembic `0018` — older enterprise tables gone  
- [ ] Biggest structural hotspots: flat huge services, `Dashboard.tsx`, `api.ts`, docs drift, dual start scripts  
