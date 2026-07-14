# Frontend Architecture

## Stack

- React 18 + TypeScript + Vite
- React Router for page navigation
- TanStack Query for API state
- Tailwind + component primitives
- Zustand for lightweight UI state
- npm workspaces (package `attendance-frontend` under monorepo root)

## Application Structure

Feature-based layout under `frontend/src/`:

- `features/auth/` — login, AuthContext, RequireAuth, permissions, session capabilities, auth API
- `features/dashboard/` — dashboard page, KPI components, insights API, analytics utils
- `features/employees/` — list/profile pages, modals, employee API
- `features/attendance/` — day board, adjustment panel, summary/log/adjust APIs, trend hooks
- `features/reports/` — reports page, charts, export utilities (Excel/PDF/Word)
- `features/operations/` — ops page, sync/metrics/commands API
- `features/settings/` — settings/profile, password, accounts API
- `features/audit/` — forensic audit capability surface (legacy route aliases redirect here)
- `components/ui/` — shared Radix/shadcn-style primitives
- `components/layout/` — AppLayout, Sidebar, TopBar
- `shared/api/client.ts` — Axios instances, auth interceptors, error helpers
- `lib/` — shared `cn`, dates
- `config/api.ts` — `VITE_API_URL` / proxy base

Vitest suites live in `frontend/tests/` (mirrors features), not colocated under `src/`.

Playwright E2E remains at repo-root `e2e/`.

## UX Domains

- **Operations Center** — queue pressure, device command visibility, sync
- **Attendance** — daily summaries, corrections (capability-gated)
- **Dashboard** — KPIs, trends, advisory AI insights/anomalies
- **HR workforce** — employees CRUD + soft offboard

## Security Model in UI

- Access token + refresh token flow from backend auth APIs
- Route-level permission checks and session capabilities (`attendance_adjust`, `forensic_audit`)
- Hidden/disabled controls for unauthorized roles

## Environment Integration

- API base is centralized in `src/config/api.ts`
- Recommended `VITE_API_URL=/api` with Vite proxy via `VITE_DEV_PROXY_TARGET`
- Domain HTTP calls live in `features/*/api.ts`; do not hardcode hosts in components

## Reliability UX Expectations

- Loading states for long-running actions (device sync, corrections)
- Clear messaging for offline / busy device conditions
- Surface queue and device health without implying immediate hard-device consistency
