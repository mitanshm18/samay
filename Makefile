# SAMAY developer commands.
# Written for the GNU make 3.81 that ships with macOS.
# Step 1 targets are read-only. The backend-* targets (Step 2) create
# backend/.venv on first use (about 80-100 MB of development tools); they never
# install anything globally, never download Python, and never touch Docker.

SHELL := /bin/bash
PYTHON ?= python3
ENV_FILE := $(if $(wildcard .env),.env,.env.example)
# Use the Python already installed; refuse to download one. --locked keeps
# the exact versions in backend/uv.lock.
UV_RUN := cd backend && UV_PYTHON_DOWNLOADS=never uv run --locked
# Database commands (Step 4) read SAMAY_DB_PASSWORD / SAMAY_DB_PORT from .env if it
# exists; SAMAY_DATABASE_URL (used in CI) wins over them. Local database only.
DB_ENV := $(if $(wildcard .env),set -a && . ./.env && set +a &&,)
# Database and API code is covered by backend-db-test (needs the database), not backend-test.
DB_CODE := src/samay/db/*,src/samay/api/*

.DEFAULT_GOAL := help
.PHONY: help doctor doctor-ci check-docker-scope test-scripts lint-scripts check \
	backend-check-uv backend-test backend-golden backend-lint backend-typecheck backend-check \
	bill-check-file bill-validate bill-calculate bill-reconcile \
	db-up db-down db-status db-migrate backend-db-test bill-save bill-history bill-show bill-verify \
	bill-run-check api web-check-npm web-install web web-check

help: ## Show available commands
	@echo "SAMAY commands (doctor and check-docker-scope are read-only)"
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'

doctor: ## Read-only health check of this Mac and the project
	@bash scripts/doctor.sh

doctor-ci: ## Doctor in CI mode (machine-specific checks are informational)
	@bash scripts/doctor.sh --ci

check-docker-scope: ## Prove compose.yaml only touches SAMAY's own Docker resources
	@docker compose --env-file $(ENV_FILE) config --format json | $(PYTHON) scripts/check_docker_scope.py

test-scripts: ## Run the tests for the helper scripts (standard library only)
	@$(PYTHON) -m unittest discover -s scripts/tests -v

lint-scripts: ## Check shell scripts with shellcheck, if it is installed
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/*.sh && echo "shellcheck: OK"; \
	else \
		echo "shellcheck not installed; skipped (CI runs it)."; \
	fi
	@bash -n scripts/doctor.sh && echo "bash syntax: OK"

backend-check-uv:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed; see docs/development.md"; exit 1; }

backend-test: backend-check-uv ## Run backend tests with branch coverage (fails below 95%)
	@$(UV_RUN) coverage run --omit='$(DB_CODE)' -m pytest --ignore=tests/golden --ignore=tests/db --ignore=tests/api
	@$(UV_RUN) coverage report --omit='$(DB_CODE)'

backend-golden: backend-check-uv ## Golden-bill merge gate (fails until all three bills are hand-checked)
	@$(UV_RUN) pytest tests/golden

backend-lint: backend-check-uv ## Check backend style with ruff
	@$(UV_RUN) ruff check src tests migrations
	@$(UV_RUN) ruff format --check src tests migrations

backend-typecheck: backend-check-uv ## Type-check the backend with mypy --strict
	@$(UV_RUN) mypy

backend-check: backend-lint backend-typecheck backend-test backend-golden ## All backend checks

check: test-scripts lint-scripts backend-check ## Everything CI runs that needs no Docker

# Bill commands (Step 3B). FILE is a samay.bill/1 JSON file, relative to the repo root.
# Add FORMAT=json for JSON output. They only read FILE and print to the terminal.
BILL_CLI = $(UV_RUN) env PYTHONPATH=src python -m samay.cli

bill-check-file: backend-check-uv
	@test -n "$(FILE)" || { echo "Give a bill file: make $(MAKECMDGOALS) FILE=examples/bills/matching.json"; exit 2; }

bill-validate: bill-check-file ## Check a bill file (FILE=..., optional FORMAT=json)
	@$(BILL_CLI) validate "$(abspath $(FILE))" --format $(or $(FORMAT),text)

bill-calculate: bill-check-file ## Recalculate a bill (FILE=..., optional FORMAT=json)
	@$(BILL_CLI) calculate "$(abspath $(FILE))" --format $(or $(FORMAT),text)

bill-reconcile: bill-check-file ## Compare a printed bill with SAMAY (FILE=..., optional FORMAT=json)
	@$(BILL_CLI) reconcile "$(abspath $(FILE))" --format $(or $(FORMAT),text)

# Database (Step 4). Only SAMAY's own container samay-db; see docs/docker-safety.md.
db-up: ## Start SAMAY's own database (scope, disk and image checks first; never pulls)
	@bash scripts/db.sh up

db-down: ## Stop SAMAY's database; the saved data in samay_pgdata is kept
	@bash scripts/db.sh down

db-status: ## Show SAMAY's database container (read-only)
	@bash scripts/db.sh status

db-migrate: backend-check-uv ## Apply database migrations (alembic upgrade head)
	@$(DB_ENV) $(UV_RUN) alembic upgrade head

backend-db-test: backend-check-uv ## Database and API tests in throwaway samay_test_* databases (needs db-up)
	@$(DB_ENV) $(UV_RUN) coverage run --data-file=.coverage.db -m pytest tests/db tests/api
	@$(UV_RUN) coverage report --data-file=.coverage.db --include='$(DB_CODE)' --fail-under=95

DB_CLI = $(DB_ENV) $(UV_RUN) env PYTHONPATH=src python -m samay.db

# Exit code 1 from save means "not clean": a reconciliation result, already explained in
# the output, so make does not report it as an error. 2 (invalid) and 3 (database) still fail.
bill-save: bill-check-file ## Reconcile a bill and save input + report (FILE=...)
	@$(DB_CLI) save "$(abspath $(FILE))"; code=$$?; if [ $$code -eq 1 ]; then exit 0; fi; exit $$code

bill-history: backend-check-uv ## List saved bills, newest first
	@$(DB_CLI) list

bill-run-check: backend-check-uv
	@test -n "$(RUN)" || { echo "Give a saved run id: make $(MAKECMDGOALS) RUN=1"; exit 2; }

bill-show: bill-run-check ## Print a saved report exactly as produced (RUN=...)
	@$(DB_CLI) show "$(RUN)"

bill-verify: bill-run-check ## Recalculate a saved bill and compare with its saved report (RUN=...)
	@$(DB_CLI) verify "$(RUN)"

# API (Step 5). Local only: 127.0.0.1. Docs at http://127.0.0.1:8000/api/docs
API_PORT ?= 8000

api: backend-check-uv ## Run the SAMAY API on 127.0.0.1:$(API_PORT) (needs db-up and db-migrate)
	@$(DB_ENV) $(UV_RUN) env PYTHONPATH=src uvicorn samay.api.app:app --host 127.0.0.1 --port $(API_PORT)

# Frontend (Step 6). npm installs into frontend/node_modules only; nothing global.
# The dev server proxies /api to the API above (make api).
WEB_PORT ?= 5173

web-check-npm:
	@command -v npm >/dev/null || { echo "npm is not installed. Install Node.js 20 or newer first."; exit 1; }

web-install: web-check-npm ## Install the frontend's pinned packages into frontend/node_modules (npm ci)
	cd frontend && npm ci --no-audit --no-fund

web: web-check-npm ## Run the frontend on http://127.0.0.1:$(WEB_PORT) (needs web-install and make api)
	@test -d frontend/node_modules || { echo "Run make web-install first."; exit 1; }
	cd frontend && npx vite --host 127.0.0.1 --port $(WEB_PORT) --strictPort

web-check: web-check-npm ## Frontend type check, tests and production build (needs web-install)
	@test -d frontend/node_modules || { echo "Run make web-install first."; exit 1; }
	cd frontend && npm run typecheck && npm test && npm run build
