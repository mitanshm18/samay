# SAMAY developer commands.
# Written for the GNU make 3.81 that ships with macOS.
# Step 1 targets are all read-only: none of them installs, downloads,
# starts or deletes anything.

SHELL := /bin/bash
PYTHON ?= python3
ENV_FILE := $(if $(wildcard .env),.env,.env.example)

.DEFAULT_GOAL := help
.PHONY: help doctor doctor-ci check-docker-scope test-scripts lint-scripts check

help: ## Show available commands
	@echo "SAMAY commands (Milestone 1, Step 1: all read-only)"
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

check: test-scripts lint-scripts ## Everything CI runs that needs no Docker
