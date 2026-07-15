# Biometric System Software — common developer commands
#
# Usage:
#   make help
#   make install
#   make test
#   make test-backend | test-frontend | test-e2e | test-matrix
#   make test-unit | test-api | test-integration | test-workers | test-scenarios

.PHONY: help install install-backend install-frontend install-e2e \
	test test-backend test-frontend test-e2e test-e2e-list test-matrix \
	test-unit test-api test-integration test-workers test-scenarios \
	test-backend-cov sync-full report-incomplete import-softworks clean

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BACKEND := $(ROOT)backend
FRONTEND := $(ROOT)frontend
VENV := $(BACKEND)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Default test env (SQLite in-memory; no live Postgres/Redis/device required)
export DATABASE_URL ?= sqlite+pysqlite:///:memory:
export JWT_SECRET_KEY ?= local-test-secret
export AUTH_BOOTSTRAP_ADMIN_EMAIL ?= bootstrap@example.com
export AUTH_BOOTSTRAP_ADMIN_PASSWORD ?= Bootstrap123!
export DEVICE_AUTO_SYNC_ENABLED ?= false
export PYTHONPATH := $(BACKEND)
export E2E_BASE_URL ?= http://localhost:5173

help:
	@echo "Biometric System Software"
	@echo ""
	@echo "Setup"
	@echo "  make install              Install backend + npm workspaces + Playwright"
	@echo "  make install-backend      Create backend/.venv and pip install requirements.txt"
	@echo "  make install-frontend     npm install at repo root (workspaces)"
	@echo "  make install-e2e          Ensure Playwright browsers are installed"
	@echo ""
	@echo "All tests"
	@echo "  make test                 Run backend + frontend + matrix (+ e2e list)"
	@echo ""
	@echo "Individual suites"
	@echo "  make test-backend         All backend pytest (unit/api/integration/workers/scenarios)"
	@echo "  make test-unit            Backend unit tests only"
	@echo "  make test-api             Backend API tests only"
	@echo "  make test-integration     Backend integration tests only"
	@echo "  make test-workers         Backend Celery worker tests only"
	@echo "  make test-scenarios       Backend company-day scenario tests only"
	@echo "  make test-backend-cov     Backend tests with coverage report"
	@echo "  make test-frontend        Frontend Vitest suite"
	@echo "  make test-e2e             Playwright E2E (skips if UI unreachable)"
	@echo "  make test-e2e-list        List Playwright scenarios"
	@echo "  make test-matrix          Traceability matrix completeness gate"
	@echo ""
	@echo "Other"
	@echo "  make sync-full            Full device attendance pull (ignores incremental floor)"
	@echo "  make report-incomplete    List weekday days whose last punch is before 15:00"
	@echo "  make import-softworks     Import Softworks four-punch XLS (append-only, never overwrite)"
	@echo "  make clean                Remove caches and reports"

install: install-backend install-frontend install-e2e

install-backend:
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"
	"$(PIP)" install --upgrade pip
	"$(PIP)" install -r "$(BACKEND)/requirements.txt"

install-frontend:
	npm install

install-e2e: install-frontend
	npx playwright install chromium

# --- all together ---

test: test-backend test-frontend test-matrix test-e2e-list
	@echo ""
	@echo "All automated suites finished (backend + frontend + matrix + e2e list)."
	@echo "Run 'make test-e2e' when the app UI is up at $$E2E_BASE_URL."

# --- backend ---

test-backend: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/unit tests/api tests/integration tests/workers tests/e2e_scenarios -q --tb=short

test-unit: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/unit -q --tb=short

test-api: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/api -q --tb=short

test-integration: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/integration -q --tb=short

test-workers: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/workers -q --tb=short

test-scenarios: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/e2e_scenarios -q --tb=short

test-backend-cov: $(PYTEST)
	cd "$(BACKEND)" && "$(PYTEST)" tests/unit tests/api tests/integration tests/workers tests/e2e_scenarios \
		--cov=app --cov-report=term-missing -q --tb=short

$(PYTEST):
	@$(MAKE) install-backend

# --- frontend / e2e / matrix ---

test-frontend:
	npm run test -w attendance-frontend

test-e2e:
	npx playwright test --config=e2e/playwright.config.ts

test-e2e-list:
	npx playwright test --config=e2e/playwright.config.ts --list

test-matrix: $(PYTHON)
	"$(PYTHON)" "$(ROOT)scripts/check_traceability_matrix.py"

$(PYTHON):
	@$(MAKE) install-backend

# Live device / DB helpers (do not use in-memory DATABASE_URL from this Makefile)
sync-full:
	cd "$(BACKEND)" && env -u DATABASE_URL "$(PYTHON)" scripts/sync_from_device.py

report-incomplete:
	cd "$(BACKEND)" && env -u DATABASE_URL "$(PYTHON)" scripts/report_incomplete_days.py

# Softworks monthly Four-Punch XLS → attendance_logs (idempotent inserts only).
# Default source: imports/Attendance or Attendance/Attendance
import-softworks:
	cd "$(BACKEND)" && env -u DATABASE_URL "$(PYTHON)" scripts/import_softworks_attendance.py

import-softworks-rebuild-sessions:
	cd "$(BACKEND)" && env -u DATABASE_URL "$(PYTHON)" scripts/import_softworks_attendance.py --rebuild-sessions-only

clean:
	rm -rf "$(BACKEND)/.pytest_cache" "$(BACKEND)/htmlcov" "$(BACKEND)/.coverage"
	rm -rf "$(FRONTEND)/coverage" "$(ROOT)playwright-report" "$(ROOT)test-results" "$(ROOT)e2e/playwright-report"
	find "$(BACKEND)" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
