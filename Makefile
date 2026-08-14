# Biometric System Software — developer commands
#
#   make help
#   make install
#   make start          # local: API + Celery + Vite (Ctrl+C stops all)
#   make start-vm       # VM LAN runner
#   make test
#   make test-e2e
#   make clean

.PHONY: help install start start-vm test test-e2e sync-full clean

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BACKEND := $(ROOT)backend
FRONTEND := $(ROOT)frontend
VENV := $(BACKEND)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Applied only to test targets (never to start / sync — those use backend/.env)
TEST_ENV := \
	DATABASE_URL=sqlite+pysqlite:///:memory: \
	JWT_SECRET_KEY=local-test-secret \
	AUTH_BOOTSTRAP_ADMIN_EMAIL=bootstrap@example.com \
	AUTH_BOOTSTRAP_ADMIN_PASSWORD=Bootstrap123! \
	DEVICE_AUTO_SYNC_ENABLED=false \
	PYTHONPATH=$(BACKEND) \
	CSRF_ENABLED=false

E2E_BASE_URL ?= http://localhost:5173

help:
	@echo "Biometric System Software"
	@echo ""
	@echo "  make install     Backend venv + npm workspaces + Playwright Chromium"
	@echo "  make start       Start API, Celery, and Vite locally (Ctrl+C stops all)"
	@echo "  make start-vm    Start stack for VM / LAN (npm run start:vm)"
	@echo "  make test        Backend pytest + frontend Vitest + traceability matrix"
	@echo "  make test-e2e    Playwright E2E (app must be up at $(E2E_BASE_URL))"
	@echo "  make sync-full   Full device attendance pull (uses backend/.env)"
	@echo "  make clean       Remove caches and reports"

install:
	@test -d "$(VENV)" || python3 -m venv "$(VENV)"
	"$(PIP)" install --upgrade pip
	"$(PIP)" install -r "$(BACKEND)/requirements.txt"
	npm install
	npx playwright install chromium

start: $(PYTHON)
	@test -d "$(ROOT)node_modules" || $(MAKE) install
	@echo "[make] Running migrations..."
	cd "$(BACKEND)" && "$(PYTHON)" -m alembic upgrade head
	@echo "[make] Starting local stack (API :8000, UI :5173)..."
	cd "$(ROOT)" && \
		VM_HOST=127.0.0.1 \
		OPEN_BROWSER=1 \
		API_BIND_HOST=0.0.0.0 \
		FRONTEND_BIND_HOST=0.0.0.0 \
		node scripts/start-vm.js

start-vm:
	npm run start:vm

test: $(PYTEST)
	cd "$(BACKEND)" && env $(TEST_ENV) "$(PYTEST)" \
		tests/unit tests/api tests/integration tests/workers tests/e2e_scenarios -q --tb=short
	npm run test -w attendance-frontend
	env $(TEST_ENV) "$(PYTHON)" "$(ROOT)scripts/check_traceability_matrix.py"
	@echo ""
	@echo "Unit/API/integration/frontend/matrix finished."
	@echo "Run 'make test-e2e' when the UI is up at $(E2E_BASE_URL)."

test-e2e:
	E2E_BASE_URL="$(E2E_BASE_URL)" npx playwright test --config=e2e/playwright.config.ts

sync-full: $(PYTHON)
	cd "$(BACKEND)" && "$(PYTHON)" scripts/sync_from_device.py

clean:
	rm -rf "$(BACKEND)/.pytest_cache" "$(BACKEND)/htmlcov" "$(BACKEND)/.coverage"
	rm -rf "$(FRONTEND)/coverage" "$(FRONTEND)/dist"
	rm -rf "$(ROOT)playwright-report" "$(ROOT)test-results" "$(ROOT)e2e/playwright-report" "$(ROOT)e2e/test-results"
	rm -f "$(BACKEND)/celerybeat-schedule" "$(BACKEND)/celerybeat-schedule.db"
	find "$(BACKEND)" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

$(PYTHON) $(PYTEST):
	@$(MAKE) install
