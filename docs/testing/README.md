# Testing documentation

- [TESTING_STRATEGY.md](./TESTING_STRATEGY.md) — layers, business rules, tooling, CI
- [TRACEABILITY_MATRIX.md](./TRACEABILITY_MATRIX.md) — every route/model/task/page → test ID

All Python deps (runtime + test) live in a single file: `backend/requirements.txt`.

## Commands (Makefile)

```bash
make help                 # list targets
make install              # backend venv + frontend npm + Playwright

make test                 # backend + frontend + matrix + e2e list
make test-backend         # all backend pytest
make test-unit            # backend unit only
make test-api             # backend API only
make test-integration     # backend integration only
make test-workers         # Celery worker tests only
make test-scenarios       # company-day scenario tests only
make test-backend-cov     # backend with coverage
make test-frontend        # Vitest
make test-e2e             # Playwright (skips if UI unreachable)
make test-e2e-list        # list Playwright scenarios
make test-matrix          # traceability gate
```
