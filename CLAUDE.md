# Open Context Graph — Agent guide

> **This file is duplicated to `AGENTS.md` (canonical) and `.cursor/rules/opencg.mdc` so the three tools that respect different file conventions all see the same instructions. If you update one, update the others.**

You are working on **Open Context Graph** (openCG) — an open-source, self-hostable enterprise context-engineering pipeline that exposes a private knowledge catalogue to any AI tool through MCP. Read this file before doing anything else.

## Project rule #1: OpenSpec is mandatory for every feature

**Every feature, deviation, or course-correction MUST go through the OpenSpec change workflow before any code is written.** No exceptions for "obvious" features. No inline annotations in another change's `tasks.md` to capture a scope cut. No undocumented architectural pivots.

This applies to:

- New features
- Scope cuts (e.g., picking a thin-MVP subset of a larger change)
- Architectural pivots discovered during implementation (e.g., "the chosen provider doesn't support the operation we need")
- Adding or removing significant dependencies
- Anything that adds, changes, or removes a requirement or scenario in the spec

**The workflow:**

1. `openspec new change <kebab-case-name>` — creates the scaffold
2. Write `proposal.md` — why + what + capabilities + impact
3. Write `design.md` (decisions with rationale, alternatives, risks, open questions) AND `specs/<capability>/spec.md` (testable WHEN/THEN scenarios using SHALL/MUST)
4. Write `tasks.md` — the implementation checklist organised by phase
5. `openspec validate <name> --strict` — MUST pass before you proceed
6. **Stop and show the user the proposal for explicit approval before implementing**
7. Implement phase by phase. Run tests as you go.
8. Run the smoke and e2e suites against the live stack (`make smoke`, `make e2e`)
9. Commit + push

**Exception**: tiny fixes that don't change a requirement or scenario (typo, lint, dependency bump, perf tweak in an existing function) are code-only OK. When in doubt, write the proposal.

**The strict workflow is non-negotiable.** Skipping it created bugs and confusion early in the project. The user reset that expectation explicitly; honor it.

## In-flight changes

```
add-foundation                — full v0 vision (canonical aspiration; delivered per capability by follow-up changes)
```

Everything else has shipped and is archived under `openspec/changes/archive/` (including `prepare-open-source-release`, the v0.1.0 release work, and `bootstrap-thin-mvp`, archived as superseded); the merged baseline is in `openspec/specs/`. `main` is protected: changes land through pull requests with one approving review and green `static`, `stack`, `observability` and `dependency-review` checks.

Check the live state any time with `openspec list`.

## Stack at a glance

| Concern | Choice |
|---|---|
| Monorepo | `pnpm` + `uv` workspaces |
| MCP server | TypeScript (`@modelcontextprotocol/sdk`) |
| Pipeline, ingestion, workers | Python 3.12 (FastAPI, asyncpg, httpx) |
| Vector store | Qdrant |
| Catalog + audit + graph | PostgreSQL 16 + Apache AGE (graph extension) |
| Cache · admin UI sessions | Valkey |
| Identity · policy | Any OIDC issuer (`OPENCG__AUTH__MODE=oidc`; bundled Keycloak under the `idp` profile); OPA for entitlement + action decisions (`infra/opa/`) |
| Embeddings | Ollama (compose-internal `ollama` service, default `nomic-embed-text`) |
| Chat / generation | Ollama Cloud (`gemma4:31b` default, used by knowledge-graph text extraction) |
| Admin UI | Next.js 16 App Router (React 19) |
| Storybook | **`@storybook/react-vite`** (NOT `@storybook/nextjs`) |
| Tests | pytest, vitest, Playwright (admin UI e2e) |
| Compose | Docker, `dev` profile only |
| Observability | OpenTelemetry → Collector (always on); Prometheus `v3.15.1`, Tempo `3.1.1`, Grafana `13.2.5` only in the opt-in overlay (`make up-obs`), never in the default stack |

## Project conventions

- **TypeScript imports**: the admin UI uses `bundler` moduleResolution; do NOT add `.js` extensions to app-code imports.
- **Python tests against asyncpg**: use a fake `_Pool` / `_Conn` pattern that records SQL + args. See `services/pipeline/tests/test_catalog.py` for the canonical example.
- **Admin UI components**: every shared component lives in `src/components/` and MUST have a `*.stories.tsx` neighbour. The `add-admin-vector-and-content` admin-ui spec is load-bearing on this rule.
- **Client → pipeline calls**: client components go through Next route handlers under `src/app/api/proxy/...`. The pipeline URL is compose-internal, not reachable from the browser.
- **Compose ports**: use `${OPENCG__SERVICE__HOST_PORT:-default}` so collisions can be dodged via `.env`.
- **Audit logs are append-only**: enforced by triggers on `opencg.audit_log` and `opencg.graph_audit_log`. Don't UPDATE them; write a state-transition row instead.
- **Token accounting on every model call**: emit an OTel span attribute AND increment `opencg_tokens_total{stage,model,provider,tenant,direction}`. The spec's "per-stage token accounting" requirement is non-negotiable.
- **Metrics and dashboards**: every service serves `/metrics`; metric families live in `packages/shared-py/src/opencg_shared/metrics.py` (the MCP server mirrors two in `services/mcp-server/src/metrics.ts`). Ingestion runs in Prometheus multiprocess mode, so use only counters and histograms there (a gauge needs a `multiprocess_mode`). Dashboards are JSON in `infra/grafana/dashboards/`; `make check-dashboards` fails on an `opencg_*` metric the shared module doesn't define. The observability overlay is opt-in: never add Prometheus, Tempo or Grafana to the default `dev` stack or the `stack` CI job.
- **Best-effort extraction**: ingest-time chat-model calls (the knowledge-graph text extractor) MUST NOT fail the ingest on extractor errors. Log + counter + continue.

## Where stuff lives

```
openspec/changes/<name>/            in-flight changes (proposal + design + specs + tasks)
openspec/specs/                     archived spec baseline (empty until first archive)
openspec/project.md                 project context loaded by OpenSpec skills
packages/shared/                    TS wire types
packages/shared-py/                 Python mirrors + OTel + Prom + config loader
services/mcp-server/                TS stdio MCP server + HTTP health endpoints
services/pipeline/                  FastAPI retrieve + admin + (soon) graph routes
services/ingestion/                 FastAPI + Click CLI
services/admin-ui/                  Next.js 16 admin UI + Storybook
infra/postgres/                     Dockerfile + init SQL (010_, 020_, ...)
infra/opa/                          OPA policies (Rego), data and policy tests
infra/keycloak/                     bundled Keycloak realm import + entrypoint
infra/ollama/                       entrypoint + healthcheck scripts
infra/otel/                         collector config (+ otel-collector.tempo.yaml for the overlay)
infra/prometheus/                   prometheus.yml (observability overlay only)
infra/tempo/                        tempo.yaml, Tempo 3 monolithic (observability overlay only)
infra/grafana/                      provisioning/ + dashboards/*.json (observability overlay only)
infra/compose/docker-compose.yml    the v0 dev profile
infra/compose/docker-compose.oidc.yml  test overlay: every service in oidc mode against the bundled Keycloak (OPENCG_TEST_AUTH_MODE=oidc, the default)
infra/compose/docker-compose.observability.yml  opt-in Prometheus/Tempo/Grafana overlay (make up-obs)
tests/smoke/run.sh                  end-to-end smoke (helpers in tests/smoke/lib.sh); SMOKE_OBS=1 = make smoke-obs
scripts/                            check-agent-guides.sh, check-dashboards.py (+ tests/)
services/admin-ui/e2e/              Playwright e2e suite (make e2e); scripts/hydration-stress.cjs (make hydration-stress)
.github/                            CI workflow, Dependabot, ruleset, templates
docs/OPERATIONS.md                  operator runbook
```

## Secrets

- `.env` is gitignored. NEVER commit it.
- The Ollama Cloud API key in `.env` is **chat-only** — Cloud's `/api/embed` is gated on the reference account (probe documented in `openspec/changes/archive/2026-11-10-bootstrap-thin-mvp/design.md` D1). Don't try to use it for embeddings.
- Run `git diff --cached | grep -iE "bearer [a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9]{20,}|<your-known-key>"` before pushing.

## Quickstart

```bash
cp .env.example .env
make up-d                                                    # build + start
make ingest-git REPO=https://github.com/anthropics/anthropic-cookbook
make smoke && make e2e                                       # end-to-end verification
make up-obs && make smoke-obs                               # OPTIONAL: Prometheus/Tempo/Grafana (Grafana on :3030)
open http://localhost:3000                                   # admin UI
```

Admin UI pages: `/` (overview), `/graph`, `/vectors`, `/entities`, `/queries`, `/ingestion`.

## Common gotchas (learned the hard way)

- **Apache AGE image tags** look like `release_PG16_1.6.0`. There is no `PG16_latest` tag.
- **Ollama image tags** are `0.30.x`. There is no `0.5` tag.
- **Postgres init script ordering**: our SQL files start at `010_` so Apache AGE's own bundled `00-create-extension-age.sql` runs first. Don't rename our files back to `00X_` or you'll fight a duplicate-extension error.
- **`uv sync --package X --package Y` does not work**. Use `uv sync --all-packages` or one `--package` at a time.
- **Storybook 8 + Next**: `@storybook/nextjs` chokes on a Next webpack hook (found on 15.5). We use `@storybook/react-vite` with tiny `next/link` + `next/navigation` mocks in `.storybook/mocks/`.
- **Bumping Next.js**: `next build` rewrites `services/admin-ui/tsconfig.json` and `next-env.d.ts`; commit them with the bump. Run the full `make hydration-stress` on every Next or React bump (issue #2 only showed under concurrent load).
- **Compose shell-var escaping**: use `$$VAR` inside healthcheck CMD-SHELL strings so the container shell — not docker compose — evaluates the substitution.
- **Auth host ports**: OPA debugging port 8281 (8181 is the MCP server), bundled Keycloak 8380 (8080 collides, see below). Both via `OPENCG__OPA__HOST_PORT` / `OPENCG__KEYCLOAK__HOST_PORT`.
- **Auth defaults fail safe**: an unset `OPENCG__ENVIRONMENT` means `production` (API keys refused); `none` auth mode refuses non-loopback `OPENCG__BIND_ADDRESS`. Every new pipeline route needs an entry in `services/pipeline/src/opencg_pipeline/security.py` `ROUTE_ACTIONS` (a unit test fails otherwise). After editing `infra/opa/`, run `make opa-revision && make opa-test`.
- **Port 8080 collision** on the user's machine (something called `nominatim` runs there). The MCP server uses host port 8181, configurable via `OPENCG__MCP__HOST_PORT`.
- **asyncpg + JSONB columns**: serialise dicts with `json.dumps(...)` before binding. Otherwise: `invalid input for query argument: expected str, got dict`.
- **MEMORY.md and per-user memory** live in `~/.claude/projects/...`, NOT in the repo. A new session won't see them. That's why this file exists.

## Working with the spec from the CLI

```bash
openspec list                                  # in-flight changes
openspec list --specs                          # archived baseline
openspec show add-knowledge-graph              # render a change
openspec validate <name> --strict              # MUST pass before implementation
openspec status --change <name>                # progress
```

When you finish implementing a change, the workflow ends with `openspec archive <name>` (consult the OpenSpec skill files in `.claude/skills/openspec-archive-change/` for the full procedure). It merges the change's spec deltas into `openspec/specs/`; use `--skip-specs` only for a change archived as superseded.

## When in doubt

Stop. Ask the user. The OpenSpec workflow exists so the user has a chance to course-correct before code is written. Use it.
