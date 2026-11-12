SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env
# OPTIONAL observability overlay (Prometheus, Tempo, Grafana): only `make up-obs`
# and `make smoke-obs` apply it. See docs/OPERATIONS.md § Observability.
COMPOSE_OBS := docker compose -f infra/compose/docker-compose.yml \
	-f infra/compose/docker-compose.observability.yml --env-file .env
# Pinned so local runs and CI validate with the same OpenSpec and gitleaks.
OPENSPEC := npx -y @fission-ai/openspec@1.4.1
GITLEAKS_IMAGE := zricethezav/gitleaks:v8.30.1
# Same tag as the `opa` compose service; runs the Rego tests with no host install.
OPA_IMAGE := openpolicyagent/opa:1.21.4
OPA_RUN := docker run --rm -v "$(CURDIR)/infra/opa:/policy:ro" -w /policy $(OPA_IMAGE)

# The bundled Keycloak (compose profile `idp`) starts only when
# OPENCG__AUTH__MODE=oidc and the issuer is unset or points at it (localhost /
# 127.0.0.1 on the Keycloak host port, or the `keycloak` service). The shell
# environment wins over .env, as it does for docker compose itself.
env_value = $(or $($(1)),$(shell sed -n 's/^[[:space:]]*$(1)=//p' .env 2>/dev/null | tail -n 1 | tr -d "\"'"))
AUTH_MODE := $(call env_value,OPENCG__AUTH__MODE)
OIDC_ISSUER := $(call env_value,OPENCG__AUTH__OIDC__ISSUER)
KEYCLOAK_HOST_PORT := $(or $(call env_value,OPENCG__KEYCLOAK__HOST_PORT),8380)
BUNDLED_ISSUER := $(strip $(findstring //localhost:$(KEYCLOAK_HOST_PORT)/,$(OIDC_ISSUER))$(findstring //127.0.0.1:$(KEYCLOAK_HOST_PORT)/,$(OIDC_ISSUER))$(findstring //keycloak:,$(OIDC_ISSUER)))
BUNDLED_IDP := $(if $(filter oidc,$(AUTH_MODE)),$(if $(OIDC_ISSUER),$(BUNDLED_ISSUER),yes))
PROFILES := --profile dev $(if $(BUNDLED_IDP),--profile idp)
# down/down-v always name `idp` so a Keycloak started earlier is removed too.
PROFILES_ALL := --profile dev --profile idp

.PHONY: help bootstrap up up-d up-obs down down-v logs ps db-apply opa-test opa-revision test test-mcp test-shared test-pipeline test-ingestion test-ui test-scripts lint typecheck format smoke smoke-cloud smoke-obs e2e e2e-ui hydration-stress ingest-git storybook check-agent-guides check-dashboards openspec-validate secrets-scan ci ci-static ci-stack api-key

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z0-9_-]+:.*?##/ {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install JS + Python deps (incl. dev tools: pytest, ruff, Playwright Chromium) locally
	pnpm install --frozen-lockfile
	uv sync --all-packages --frozen
	pnpm --filter @opencg/admin-ui exec playwright install chromium

up: ## Start the dev stack (foreground)
	$(COMPOSE) $(PROFILES) up

up-d: ## Start the dev stack (detached; adds the bundled Keycloak in oidc mode)
	$(COMPOSE) $(PROFILES) up -d

up-obs: ## OPTIONAL: dev stack + Prometheus/Tempo/Grafana overlay (detached, ~700 MB more RAM)
	$(COMPOSE_OBS) $(PROFILES) up -d --wait

# The observability overlay's files are passed too, so its containers and
# volumes are removed whether or not it was applied; --remove-orphans catches
# the smoke/e2e overlay services.
down: ## Stop the stack (and any overlay, incl. observability) and remove containers
	$(COMPOSE_OBS) $(PROFILES_ALL) down --remove-orphans

down-v: ## Stop the stack (and any overlay) and DELETE volumes, incl. Prometheus/Tempo/Grafana data
	$(COMPOSE_OBS) $(PROFILES_ALL) down -v --remove-orphans

logs: ## Tail logs
	$(COMPOSE) logs -f

ps: ## List services
	$(COMPOSE) ps

# Init scripts run only when the Postgres volume is first created. This applies
# one of them (all are re-runnable) to an existing volume, as the superuser the
# image created. .sh scripts run in the container's shell with its environment.
db-apply: ## Apply an init script to an existing Postgres volume: `make db-apply SQL=070_access_audit.sql`
	@test -n "$(SQL)" || { echo "usage: make db-apply SQL=<file in infra/postgres/init>" >&2; exit 2; }
	@f="infra/postgres/init/$(notdir $(SQL))"; test -f "$$f" || { echo "no such init script: $$f" >&2; exit 2; }; \
	echo "applying $$f"; \
	case "$$f" in \
	  *.sql) $(COMPOSE) --profile dev exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 --no-psqlrc -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < "$$f" ;; \
	  *.sh)  $(COMPOSE) --profile dev exec -T postgres bash -s < "$$f" ;; \
	  *) echo "unsupported init script type: $$f" >&2; exit 2 ;; \
	esac

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

smoke: ## End-to-end smoke test (applies the overlays itself; OPENCG_TEST_AUTH_MODE=oidc (default) or none)
	./tests/smoke/run.sh

smoke-cloud: ## Bounded real-provider canary (requires chat API key)
	SMOKE_CHAT_MODE=cloud ./tests/smoke/run.sh

smoke-obs: ## OPTIONAL: smoke + observability overlay checks (Prometheus, Tempo, Grafana)
	SMOKE_OBS=1 ./tests/smoke/run.sh

e2e: ## Admin UI e2e suite (Playwright); starts the stack if needed; OPENCG_TEST_AUTH_MODE=oidc (default) or none
	$(COMPOSE) $(PROFILES) up -d --wait --no-recreate
	pnpm --filter @opencg/admin-ui e2e

hydration-stress: ## Admin UI hydration stress check (needs a seeded stack; BROWSERS=7 CYCLES=30 by default)
	BROWSERS=$(or $(BROWSERS),7) CYCLES=$(or $(CYCLES),30) \
		pnpm --filter @opencg/admin-ui exec node scripts/hydration-stress.cjs

e2e-ui: ## Playwright UI mode; leaves the e2e overlay applied between runs
	$(COMPOSE) $(PROFILES) up -d --wait --no-recreate
	E2E_KEEP_OVERLAY=1 pnpm --filter @opencg/admin-ui e2e:ui

storybook: ## Build the admin UI Storybook (static output is gitignored)
	pnpm --filter @opencg/admin-ui build-storybook

opa-test: ## OPA policy tests (`opa test`), format + strict check, and the meta.revision staleness check
	$(OPA_RUN) check --strict policies data
	$(OPA_RUN) fmt --list --fail policies
	$(OPA_RUN) test --verbose=false policies data
	python3 infra/opa/revision.py --check

api-key: ## Print a new dev-only API key and its key-file entry: `make api-key NAME=ci ROLES=reader`
	@python3 scripts/new-api-key.py "$(NAME)" "$(PRINCIPAL)" "$(or $(ROLES),reader)"

opa-revision: ## Recompute infra/opa/data/opencg.json meta.revision after editing a policy or data file
	python3 infra/opa/revision.py --write

check-agent-guides: ## Fail if the AGENTS.md / CLAUDE.md / .cursor/rules/opencg.mdc bodies differ
	./scripts/check-agent-guides.sh

check-dashboards: ## Lint the Grafana dashboards (and promtool-check prometheus.yml when Docker is up)
	uv run --package opencg-shared python scripts/check-dashboards.py

openspec-validate: ## Strictly validate every OpenSpec change and spec
	$(OPENSPEC) validate --all --strict

# Branches and tags only: local tool refs (for example refs/t3/* checkpoints) are
# never pushed, and a fresh clone in CI has none.
secrets-scan: ## Scan the full git history of branches and tags for secrets (gitleaks, via Docker)
	docker run --rm -v "$(CURDIR):/repo" $(GITLEAKS_IMAGE) detect --source /repo --redact --no-banner \
		--log-opts="--branches --tags"

ci-static: lint typecheck test opa-test storybook check-agent-guides check-dashboards openspec-validate secrets-scan ## CI's static job, locally

ci-stack: ## CI's stack job, locally: start the stack, then smoke and e2e (needs .env)
	$(COMPOSE) $(PROFILES) up -d --wait
	$(MAKE) smoke
	$(MAKE) e2e

ci: ci-static ci-stack ## The whole CI gate, locally
