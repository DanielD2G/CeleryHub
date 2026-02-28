# ──────────────────────────────────────────────
# CeleryHub — Vite + Hono + celery-gateway
# ──────────────────────────────────────────────
#
#   make dev          → run Hono + Vite + celery-gateway together
#   make install      → install deps for all projects
#   make gateway      → run only the Python gateway
#   make server       → run only the Hono server
#   make web          → run only the Vite dev server
#
# Both services read CELERY_BROKER_URL from .env.local.
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
CELERY_GATEWAY_URL  ?= http://localhost:8000
CELERY_GATEWAY_PORT ?= 8000
SERVER_PORT         ?= 3000
VITE_PORT           ?= 5173

# Colors
_cyan  := \033[36m
_reset := \033[0m

# ── Install ──────────────────────────────────

.PHONY: install install-bun install-gateway

install: install-bun install-gateway ## Install all dependencies

install-bun:
	@echo -e "$(_cyan)▸ Installing dependencies (bun workspaces)...$(_reset)"
	bun install

install-gateway:
	@echo -e "$(_cyan)▸ Installing celery-gateway dependencies...$(_reset)"
	cd $(GATEWAY_DIR) && uv venv --python 3.11 && uv pip install -e . --python .venv/bin/python

# ── Dev (all services) ───────────────────────

.PHONY: dev stop

define _kill_ports
	@for port in $(CELERY_GATEWAY_PORT) $(SERVER_PORT) $(VITE_PORT); do \
		pids=$$(lsof -ti :$$port 2>/dev/null); \
		if [ -n "$$pids" ]; then \
			echo "Killing port $$port (pid $$pids)"; \
			echo "$$pids" | xargs kill -9 2>/dev/null || true; \
		fi; \
	done
endef

dev: _ensure-deps ## Run Hono server + Vite + celery-gateway in parallel
	@trap '$(MAKE) --no-print-directory stop; exit 0' INT TERM; \
	echo -e "$(_cyan)▸ Starting celery-gateway on :$(CELERY_GATEWAY_PORT)...$(_reset)"; \
	$(GATEWAY_VENV)/bin/uvicorn celery_gateway.main:app \
	   --host 0.0.0.0 --port $(CELERY_GATEWAY_PORT) --reload \
	   --app-dir $(GATEWAY_DIR)/src & \
	echo -e "$(_cyan)▸ Starting Hono server on :$(SERVER_PORT)...$(_reset)"; \
	CELERY_GATEWAY_URL=$(CELERY_GATEWAY_URL) \
	 PORT=$(SERVER_PORT) \
	 bun run --filter @celeryhub/server dev & \
	echo -e "$(_cyan)▸ Starting Vite dev server on :$(VITE_PORT)...$(_reset)"; \
	bun run --filter @celeryhub/web dev & \
	wait

stop: ## Kill all dev processes (by port)
	@echo -e "$(_cyan)▸ Stopping services...$(_reset)"
	$(_kill_ports)
	@echo "Done."

# ── Individual services ──────────────────────

.PHONY: gateway server web

gateway: _check-gateway ## Run only celery-gateway
	$(GATEWAY_VENV)/bin/uvicorn celery_gateway.main:app \
	  --host 0.0.0.0 --port $(CELERY_GATEWAY_PORT) --reload \
	  --app-dir $(GATEWAY_DIR)/src

server: _check-bun ## Run only the Hono server
	CELERY_GATEWAY_URL=$(CELERY_GATEWAY_URL) \
	PORT=$(SERVER_PORT) \
	bun run --filter @celeryhub/server dev

web: _check-bun ## Run only the Vite dev server
	bun run --filter @celeryhub/web dev

# ── Build ────────────────────────────────────

.PHONY: build docker

build: ## Build both packages
	@echo -e "$(_cyan)▸ Building frontend (Vite)...$(_reset)"
	bun run --filter @celeryhub/web build
	@echo -e "$(_cyan)▸ Building server (TypeScript)...$(_reset)"
	bun run --filter @celeryhub/server build

docker: ## Build unified Docker image
	@echo -e "$(_cyan)▸ Building celeryhub Docker image...$(_reset)"
	docker build -t celeryhub .

# ── Health checks ────────────────────────────

.PHONY: health

health: ## Check if services are running
	@echo -n "celery-gateway: " && \
	  curl -sf $(CELERY_GATEWAY_URL)/health | python3 -m json.tool 2>/dev/null || echo "not reachable"
	@echo -n "hono-server:    " && \
	  curl -sf http://localhost:$(SERVER_PORT)/api/events -o /dev/null && echo "ok" || echo "not reachable"
	@echo -n "vite-dev:       " && \
	  curl -sf http://localhost:$(VITE_PORT) -o /dev/null && echo "ok" || echo "not reachable"

# ── Clean ────────────────────────────────────

.PHONY: clean

clean: ## Remove build artifacts
	rm -rf packages/web/dist
	rm -rf packages/server/dist
	rm -rf node_modules
	rm -rf $(GATEWAY_VENV)
	find $(GATEWAY_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── Helpers ──────────────────────────────────

.PHONY: _check-bun _check-gateway _ensure-deps

_check-bun:
	@test -d node_modules || { echo "Run 'make install' first"; exit 1; }

_check-gateway:
	@test -f $(GATEWAY_VENV)/bin/uvicorn || { echo "Run 'make install' first"; exit 1; }

_ensure-deps: _ensure-bun _ensure-gateway

_ensure-bun:
	@test -d node_modules || { echo -e "$(_cyan)▸ Installing dependencies...$(_reset)" && bun install; }

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
