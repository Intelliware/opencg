SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env

.PHONY: help bootstrap up up-d down logs ps test test-mcp test-pipeline test-ingestion test-ui test-explainer lint format smoke smoke-cloud ingest-git explainer explainer-check explainer-open

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install JS + Python deps locally
	pnpm install
	uv sync

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

test: test-mcp test-pipeline test-ingestion test-ui test-explainer ## Run all unit tests

test-mcp:
	pnpm --filter @opencg/mcp-server test

test-pipeline:
	uv run --package opencg-pipeline pytest services/pipeline/tests

test-ingestion:
	uv run --package opencg-ingestion pytest services/ingestion/tests

test-ui:
	pnpm --filter @opencg/admin-ui test

# The explainer generator is stdlib-only and lives outside the uv workspace, so
# pytest comes from an overlay rather than becoming a project dependency.
test-explainer:
	uv run --with pytest pytest tools/explainer/tests
	node tools/explainer/tests/smoke_render.js

lint:
	pnpm -r lint
	uv run ruff check .

format:
	pnpm -r format
	uv run ruff format .

ingest-git: ## Ingest a git repo: `make ingest-git REPO=https://github.com/...`
	$(COMPOSE) exec ingestion uv run --package opencg-ingestion python -m opencg_ingestion.cli git "$(REPO)"

smoke: ## End-to-end smoke test
	./tests/smoke/run.sh

smoke-cloud: ## Bounded real-provider canary (requires chat API key)
	SMOKE_CHAT_MODE=cloud ./tests/smoke/run.sh

explainer: ## Rebuild docs/explainer/index.html (snapshots a version if content changed)
	python3 tools/explainer/build.py

explainer-check: ## Fail if the explainer is stale vs openspec/ (for CI)
	python3 tools/explainer/build.py --check

explainer-open: explainer ## Rebuild the explainer and open it in a browser
	@python3 -c "import pathlib,webbrowser; webbrowser.open(pathlib.Path('docs/explainer/index.html').resolve().as_uri())"
