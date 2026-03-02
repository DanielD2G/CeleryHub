# ──────────────────────────────────────────────
# CeleryHub — Vite + FastAPI (unified backend)
# ──────────────────────────────────────────────
#
#   make dev          → run FastAPI + Vite dev server
#   make install      → install deps for all projects
#   make gateway      → run only the FastAPI server
#   make web          → run only the Vite dev server
#
# Read CELERY_BROKER_URL from .env.local.
# Override: CELERY_BROKER_URL=redis://myhost:6379 make dev
# ──────────────────────────────────────────────

SHELL := /bin/bash

# Paths
ROOT          := $(shell pwd)
GATEWAY_DIR   := $(ROOT)/services/celery-gateway
GATEWAY_VENV  := $(GATEWAY_DIR)/.venv

# Load .env.local so the gateway gets the same vars
-include .env.local
export

# Defaults
SERVER_PORT  ?= 3000
VITE_PORT    ?= 5173

# Colors
_cyan  := \033[36m
_reset := \033[0m

# ── Install ──────────────────────────────────

.PHONY: install install-web install-gateway

install: install-web install-gateway ## Install all dependencies

install-web:
	@echo -e "$(_cyan)▸ Installing web dependencies...$(_reset)"
	cd $(ROOT)/packages/web && npm install

install-gateway:
	@echo -e "$(_cyan)▸ Installing celery-gateway dependencies...$(_reset)"
	cd $(GATEWAY_DIR) && uv venv --python 3.11 && uv pip install -e . --python .venv/bin/python

# ── Dev (all services) ───────────────────────

.PHONY: dev stop

define _kill_ports
	@for port in $(SERVER_PORT) $(VITE_PORT); do \
		pids=$$(lsof -ti :$$port 2>/dev/null); \
		if [ -n "$$pids" ]; then \
			echo "Killing port $$port (pid $$pids)"; \
			echo "$$pids" | xargs kill -9 2>/dev/null || true; \
		fi; \
	done
endef

dev: _ensure-deps ## Run FastAPI server + Vite dev server in parallel
	@trap '$(MAKE) --no-print-directory stop; exit 0' INT TERM; \
	echo -e "$(_cyan)▸ Starting FastAPI on :$(SERVER_PORT)...$(_reset)"; \
	PORT=$(SERVER_PORT) \
	$(GATEWAY_VENV)/bin/uvicorn celery_gateway.main:app \
	   --host 0.0.0.0 --port $(SERVER_PORT) --reload \
	   --app-dir $(GATEWAY_DIR)/src & \
	echo -e "$(_cyan)▸ Starting Vite dev server on :$(VITE_PORT)...$(_reset)"; \
	cd $(ROOT)/packages/web && npx vite --port $(VITE_PORT) & \
	wait

stop: ## Kill all dev processes (by port)
	@echo -e "$(_cyan)▸ Stopping services...$(_reset)"
	$(_kill_ports)
	@echo "Done."

# ── Individual services ──────────────────────

.PHONY: gateway web

gateway: _check-gateway ## Run only the FastAPI server
	PORT=$(SERVER_PORT) \
	$(GATEWAY_VENV)/bin/uvicorn celery_gateway.main:app \
	  --host 0.0.0.0 --port $(SERVER_PORT) --reload \
	  --app-dir $(GATEWAY_DIR)/src

web: ## Run only the Vite dev server
	cd $(ROOT)/packages/web && npx vite --port $(VITE_PORT)

# ── Build ────────────────────────────────────

.PHONY: build docker

build: ## Build frontend (Vite)
	@echo -e "$(_cyan)▸ Building frontend (Vite)...$(_reset)"
	cd $(ROOT)/packages/web && npx vite build

docker: ## Build unified Docker image
	@echo -e "$(_cyan)▸ Building celeryhub Docker image...$(_reset)"
	docker build -t celeryhub .

# ── Test & Lint ──────────────────────────────

.PHONY: test lint

test: _check-gateway ## Run Python tests
	@echo -e "$(_cyan)▸ Running tests...$(_reset)"
	cd $(GATEWAY_DIR) && $(GATEWAY_VENV)/bin/pytest tests/ -v

lint: _check-gateway ## Lint Python code with ruff
	@echo -e "$(_cyan)▸ Linting Python code...$(_reset)"
	cd $(GATEWAY_DIR) && $(GATEWAY_VENV)/bin/ruff check src/ tests/

# ── Health checks ────────────────────────────

.PHONY: health

health: ## Check if services are running
	@echo -n "fastapi-server: " && \
	  curl -sf http://localhost:$(SERVER_PORT)/health | python3 -m json.tool 2>/dev/null || echo "not reachable"
	@echo -n "vite-dev:       " && \
	  curl -sf http://localhost:$(VITE_PORT) -o /dev/null && echo "ok" || echo "not reachable"

# ── Clean ────────────────────────────────────

.PHONY: clean

clean: ## Remove build artifacts and database
	rm -rf packages/web/dist
	rm -rf packages/web/node_modules
	rm -rf node_modules
	rm -rf $(GATEWAY_VENV)
	rm -f $(ROOT)/data/*.db $(ROOT)/data/*.sqlite
	find $(GATEWAY_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── Helpers ──────────────────────────────────

.PHONY: _check-gateway _ensure-deps

_check-gateway:
	@test -f $(GATEWAY_VENV)/bin/uvicorn || { echo "Run 'make install' first"; exit 1; }

_ensure-deps: _ensure-web _ensure-gateway

_ensure-web:
	@test -d $(ROOT)/packages/web/node_modules || { \
		echo -e "$(_cyan)▸ Installing web dependencies...$(_reset)" && \
		cd $(ROOT)/packages/web && npm install; \
	}

_ensure-gateway:
	@test -f $(GATEWAY_VENV)/bin/uvicorn || { \
		echo -e "$(_cyan)▸ Installing celery-gateway dependencies...$(_reset)" && \
		cd $(GATEWAY_DIR) && uv venv --python 3.11 && uv pip install -e . --python .venv/bin/python; \
	}

# ── Help ─────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*## "}; {printf "  $(_cyan)%-16s$(_reset) %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
