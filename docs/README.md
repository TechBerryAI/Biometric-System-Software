# Documentation Hub

This folder is the single source of truth for platform architecture, operations, deployment, and recovery guidance.

## Document Map

### Architecture

- [`architecture/PROJECT_STRUCTURE.md`](architecture/PROJECT_STRUCTURE.md)  
  Current, self-contained repo/architecture snapshot (prefer this when older docs conflict after schema `0018`).

- [`architecture/overview.md`](architecture/overview.md)  
  End-to-end platform architecture, boundaries, data flow, and resilience model.

- [`architecture/backend.md`](architecture/backend.md)  
  FastAPI/Celery/queue/reconciliation internals, device write lifecycle, and storage model.

- [`architecture/frontend.md`](architecture/frontend.md)  
  React app structure, routing, auth/RBAC experience, and operations center UI organization.

### API

- [`api/overview.md`](api/overview.md)  
  API domains and endpoint groups for auth, attendance, operations, insights, and health checks.

### Operations

- [`operations/reliability.md`](operations/reliability.md)  
  Queue health, replay safety, quarantine modes, and observability model.

- [`operations/deployment.md`](operations/deployment.md)  
  Local, staging, and production deployment setup including Redis/Celery and environment variables.

- [`operations/runbooks.md`](operations/runbooks.md)  
  Incident response and operator workflows: freeze mode, quarantine, dead letters, and recovery drills.

### Testing

- [`testing/TESTING_STRATEGY.md`](testing/TESTING_STRATEGY.md)  
  Test pyramid and how to run suites.

- [`testing/TRACEABILITY_MATRIX.md`](testing/TRACEABILITY_MATRIX.md)  
  Requirement-to-test mapping (enforced by `scripts/check_traceability_matrix.py`).
