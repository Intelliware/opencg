SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env

.PHONY: help bootstrap up up-d down down-v logs ps test test-mcp test-shared test-pipeline test-ingestion test-ui lint typecheck format smoke smoke-cloud e2e e2e-ui ingest-git

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z0-9_-]+:.*?##/ {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install JS + Python deps (incl. dev tools: pytest, ruff, Playwright Chromium) locally
	pnpm install --frozen-lockfile
	uv sync --all-packages --frozen
	pnpm --filter @opencg/admin-ui exec playwright install chromium

up: ## Start the dev stack (foreground)
	$(COMPOSE) --profile dev up

up-d: ## Start the dev stack (detached)
	$(COMPOSE) --profile dev up -d

down: ## Stop the stack and remove containers
	$(COMPOSE) down

down-v: ## Stop the stack and DELETE volumes
	$(COMPOSE) down -v

logs: ## Tail logs
	$(COMPOSE) logs -f

ps: ## List services
	$(COMPOSE) ps

test: test-mcp test-shared test-pipeline test-ingestion test-ui ## Run all unit tests

test-mcp:
	pnpm --filter @opencg/mcp-server test

test-shared:
	uv run --package opencg-shared pytest packages/shared-py/tests

test-pipeline:
	uv run --package opencg-pipeline pytest services/pipeline/tests

test-ingestion:
	uv run --package opencg-ingestion pytest services/ingestion/tests

test-ui:
	pnpm --filter @opencg/admin-ui test

lint: ## Lint TS (eslint/tsc) and Python (ruff check + format check)
	pnpm -r lint
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Type-check every TS package
	pnpm --filter @opencg/shared build
	pnpm -r typecheck

format:
	pnpm -r format
	uv run ruff format .

ingest-git: ## Ingest a git repo: `make ingest-git REPO=https://github.com/...`
	$(COMPOSE) exec ingestion uv run --package opencg-ingestion python -m opencg_ingestion.cli git "$(REPO)"

smoke: ## End-to-end smoke test (applies the smoke overlay itself)
	./tests/smoke/run.sh

smoke-cloud: ## Bounded real-provider canary (requires chat API key)
	SMOKE_CHAT_MODE=cloud ./tests/smoke/run.sh

e2e: ## Admin UI end-to-end suite (Playwright); starts the stack first if needed
	$(COMPOSE) --profile dev up -d --wait --no-recreate
	pnpm --filter @opencg/admin-ui e2e

e2e-ui: ## Playwright UI mode; leaves the e2e overlay applied between runs
	$(COMPOSE) --profile dev up -d --wait --no-recreate
	E2E_KEEP_OVERLAY=1 pnpm --filter @opencg/admin-ui e2e:ui
