# Frontend Architecture

## Stack

- React 18 + TypeScript + Vite
- React Router for page navigation
- TanStack Query for API state
- Tailwind + component primitives
- Zustand for lightweight UI state

## Application Structure

Key paths:

- `src/pages/`
  - `Dashboard`, `Attendance`, `Employees`, `EmployeeProfile`, `Reports`, `Operations`, `Settings`, `Login`
- `src/components/layout/`
  - app shell, topbar, sidebar
- `src/components/dashboard/`
  - trend charts and insights cards
- `src/auth/`
  - auth context, route guards, permission helpers
- `src/services/api.ts`
  - HTTP client and API domain calls

## UX Domains

- **Operations Center**
  - queue pressure
  - drift and reconciliation visibility
  - dead letters and replay outcomes
  - firmware and fleet indicators
- **Governance Flows**
  - maintenance/freeze/quarantine actions (RBAC protected)
- **Attendance Insights**
  - derived session and trend analytics

## Security Model in UI

- Access token + refresh token flow from backend auth APIs
- route-level and action-level permission checks
- hidden/disabled controls for unauthorized roles

## Environment Integration

- frontend reads API base from `VITE_API_URL`
- default local target is `http://localhost:8000`

## Reliability UX Expectations

- show operation loading states for long-running actions
- display correlation/request IDs where possible for support workflows
- render degraded/quarantine/offline device modes with clear operator messaging
- surface retry/reconciliation states without implying immediate hard-device consistency
