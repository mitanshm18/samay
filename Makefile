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

.DEFAULT_GOAL := help
.PHONY: help doctor doctor-ci check-docker-scope test-scripts lint-scripts check \
	backend-check-uv backend-test backend-golden backend-lint backend-typecheck backend-check \
	bill-check-file bill-validate bill-calculate bill-reconcile

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
	@$(UV_RUN) coverage run -m pytest --ignore=tests/golden
	@$(UV_RUN) coverage report

backend-golden: backend-check-uv ## Golden-bill merge gate (fails until all three bills are hand-checked)
	@$(UV_RUN) pytest tests/golden

backend-lint: backend-check-uv ## Check backend style with ruff
	@$(UV_RUN) ruff check src tests
	@$(UV_RUN) ruff format --check src tests

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
