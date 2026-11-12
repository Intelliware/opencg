SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env
# OPTIONAL observability overlay (Prometheus, Tempo, Grafana): only `make up-obs`
# and `make smoke-obs` apply it. See docs/OPERATIONS.md § Observability.
COMPOSE_OBS := docker compose -f infra/compose/docker-compose.yml \
	-f infra/compose/docker-compose.observability.yml --env-file .env
# Pinned so local runs and CI validate with the same OpenSpec and gitleaks.
OPENSPEC := npx -y @fission-ai/openspec@1.4.1
GITLEAKS_IMAGE := zricethezav/gitleaks:v8.30.1

.PHONY: help bootstrap up up-d up-obs down down-v logs ps test test-mcp test-shared test-pipeline test-ingestion test-ui test-scripts lint typecheck format smoke smoke-cloud smoke-obs e2e e2e-ui hydration-stress ingest-git storybook check-agent-guides check-dashboards openspec-validate secrets-scan ci ci-static ci-stack

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

up-obs: ## OPTIONAL: dev stack + Prometheus/Tempo/Grafana overlay (detached, ~700 MB more RAM)
	$(COMPOSE_OBS) --profile dev up -d --wait

# The observability overlay's files are passed too, so its containers and
# volumes are removed whether or not it was applied; --remove-orphans catches
# the smoke/e2e overlay services.
down: ## Stop the stack (and any overlay, incl. observability) and remove containers
	$(COMPOSE_OBS) --profile dev down --remove-orphans

down-v: ## Stop the stack (and any overlay) and DELETE volumes, incl. Prometheus/Tempo/Grafana data
	$(COMPOSE_OBS) --profile dev down -v --remove-orphans

logs: ## Tail logs
	$(COMPOSE) logs -f

ps: ## List services
	$(COMPOSE) ps

test: test-mcp test-shared test-pipeline test-ingestion test-ui test-scripts ## Run all unit tests

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

test-scripts:
	uv run --package opencg-shared pytest scripts/tests

lint: ## Lint TS (eslint/tsc) and Python (ruff check + format check)
	pnpm --filter @opencg/shared build
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

smoke-obs: ## OPTIONAL: smoke + observability overlay checks (Prometheus, Tempo, Grafana)
	SMOKE_OBS=1 ./tests/smoke/run.sh

e2e: ## Admin UI end-to-end suite (Playwright); starts the stack first if needed
	$(COMPOSE) --profile dev up -d --wait --no-recreate
	pnpm --filter @opencg/admin-ui e2e

hydration-stress: ## Admin UI hydration stress check (needs a seeded stack; BROWSERS=7 CYCLES=30 by default)
	BROWSERS=$(or $(BROWSERS),7) CYCLES=$(or $(CYCLES),30) \
		pnpm --filter @opencg/admin-ui exec node scripts/hydration-stress.cjs

e2e-ui: ## Playwright UI mode; leaves the e2e overlay applied between runs
	$(COMPOSE) --profile dev up -d --wait --no-recreate
	E2E_KEEP_OVERLAY=1 pnpm --filter @opencg/admin-ui e2e:ui

storybook: ## Build the admin UI Storybook (static output is gitignored)
	pnpm --filter @opencg/admin-ui build-storybook

check-agent-guides: ## Fail if the AGENTS.md / CLAUDE.md / .cursor/rules/opencg.mdc bodies differ
	./scripts/check-agent-guides.sh

check-dashboards: ## Lint the Grafana dashboards (and promtool-check prometheus.yml when Docker is up)
	uv run --package opencg-shared python scripts/check-dashboards.py

openspec-validate: ## Strictly validate every OpenSpec change and spec
	$(OPENSPEC) validate --all --strict

secrets-scan: ## Scan the full git history for secrets (gitleaks, via Docker)
	docker run --rm -v "$(CURDIR):/repo" $(GITLEAKS_IMAGE) detect --source /repo --redact --no-banner

ci-static: lint typecheck test storybook check-agent-guides check-dashboards openspec-validate secrets-scan ## CI's static job, locally

ci-stack: ## CI's stack job, locally: start the stack, then smoke and e2e (needs .env)
	$(COMPOSE) --profile dev up -d --wait
	$(MAKE) smoke
	$(MAKE) e2e

ci: ci-static ci-stack ## The whole CI gate, locally
