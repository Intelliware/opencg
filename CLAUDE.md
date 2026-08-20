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
8. Run the smoke against the live stack (`bash tests/smoke/run.sh`)
9. **Run `make explainer`** to refresh `docs/explainer/index.html` and snapshot a new version
10. Commit + push

**Exception**: tiny fixes that don't change a requirement or scenario (typo, lint, dependency bump, perf tweak in an existing function) are code-only OK. When in doubt, write the proposal.

**The strict workflow is non-negotiable.** Skipping it created bugs and confusion early in the project. The user reset that expectation explicitly; honor it.

## In-flight changes

```
fix-symbol-attribution           0/27 tasks    — completeness check miscounts referenced types as lost symbols; blocks the gate below (SPECCED; awaiting approval)
add-incremental-ingest           0/60 tasks    — skip files already finished and unchanged (SPECCED; T1 built, awaiting approval)
add-ontology-layer               0/83 tasks    — concept classes + domain/range constraints (SPECCED; PARKED — see below)
bootstrap-thin-mvp               63/87 tasks   — original thin-MVP contract (substantially shipped)
add-foundation                   0/104 tasks   — full v0 vision (canonical aspiration; superseded per-capability by follow-ups)
```

**Current focus is the ingestion pillar. `add-ontology-layer` is parked and NOT in scope** — do not start it without asking. Two reasons: it and `add-incremental-ingest` both touch code around `graph_writer.py`, and it defers backfilling unclassified concepts on the assumption that re-ingest reprocesses everything for free, which `add-incremental-ingest` removes. That interaction is handled by an `extraction_version` in the completion marker, but the two changes must not be implemented concurrently.

**Sequencing within the ingestion work**: `fix-symbol-attribution` must land before `add-incremental-ingest` enables its gate (that change's task 5). It does not block the earlier tasks — withholding a completion marker from a degraded file is correct either way. Without the fix, 63% of Python files would be reprocessed on every run forever.

Fourteen changes are already archived under `openspec/changes/archive/`, including `add-knowledge-graph` and `add-admin-vector-and-content`. Archived changes do not appear in `openspec list`; their requirements live in `openspec/specs/`.

Check the live state any time with `openspec list`.

## Stack at a glance

| Concern | Choice |
|---|---|
| Monorepo | `pnpm` + `uv` workspaces |
| MCP server | TypeScript (`@modelcontextprotocol/sdk`) |
| Pipeline, ingestion, workers | Python 3.12 (FastAPI, asyncpg, httpx) |
| Vector store | Qdrant |
| Catalog + audit + graph | PostgreSQL 16 + Apache AGE (graph extension) |
| Cache | Valkey |
| Embeddings | Ollama (compose-internal `ollama` service, default `nomic-embed-text`) |
| Chat / generation | Ollama Cloud (`gemma3:4b` default, used by upcoming knowledge-graph extraction) |
| Admin UI | Next.js 15 App Router |
| Storybook | **`@storybook/react-vite`** (NOT `@storybook/nextjs`) |
| Tests | pytest, vitest |
| Compose | Docker, `dev` profile only |

## Project conventions

- **TypeScript imports**: the admin UI uses `bundler` moduleResolution; do NOT add `.js` extensions to app-code imports.
- **Python tests against asyncpg**: use a fake `_Pool` / `_Conn` pattern that records SQL + args. See `services/pipeline/tests/test_catalog.py` for the canonical example.
- **Admin UI components**: every shared component lives in `src/components/` and MUST have a `*.stories.tsx` neighbour. The `add-admin-vector-and-content` admin-ui spec is load-bearing on this rule.
- **Client → pipeline calls**: client components go through Next route handlers under `src/app/api/proxy/...`. The pipeline URL is compose-internal, not reachable from the browser.
- **Compose ports**: use `${OPENCG__SERVICE__HOST_PORT:-default}` so collisions can be dodged via `.env`.
- **Audit logs are append-only**: enforced by triggers on `opencg.audit_log` and `opencg.graph_audit_log`. Don't UPDATE them; write a state-transition row instead.
- **Token accounting on every model call**: emit an OTel span attribute AND increment `opencg_tokens_total{stage,model,provider,tenant,direction}`. The spec's "per-stage token accounting" requirement is non-negotiable.
- **Best-effort extraction**: ingest-time chat-model calls (the upcoming knowledge-graph extractor) MUST NOT fail the ingest on extractor errors. Log + counter + continue.

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
services/admin-ui/                  Next.js 15 admin UI + Storybook
infra/postgres/                     Dockerfile + init SQL (010_, 020_, ...)
infra/ollama/                       entrypoint + healthcheck scripts
infra/compose/docker-compose.yml    the v0 dev profile
tests/smoke/run.sh                  end-to-end smoke
tools/explainer/                    architecture-explainer generator (stdlib-only)
docs/explainer/index.html           generated interactive explainer (self-contained)
docs/explainer/versions/            one JSON snapshot per explainer version
docs/OPERATIONS.md                  operator runbook
```

## Secrets

- `.env` is gitignored. NEVER commit it.
- The Ollama Cloud API key in `.env` is **chat-only** — Cloud's `/api/embed` is gated on the reference account (probe documented in `openspec/changes/bootstrap-thin-mvp/design.md` D1). Don't try to use it for embeddings.
- Run `git diff --cached | grep -iE "bearer [a-zA-Z0-9]{20,}|sk-[a-zA-Z0-9]{20,}|<your-known-key>"` before pushing.

## Quickstart

```bash
cp .env.example .env
make up-d                                                    # build + start
make ingest-git REPO=https://github.com/anthropics/anthropic-cookbook
bash tests/smoke/run.sh                                      # e2e verification
open http://localhost:3000                                   # admin UI
```

Admin UI pages: `/queries`, `/vectors`, `/entities`, `/ingestion`, `/graph`. (`/ontology` once `add-ontology-layer` ships.)

## Common gotchas (learned the hard way)

- **Apache AGE image tags** look like `release_PG16_1.6.0`. There is no `PG16_latest` tag.
- **Ollama image tags** are `0.30.x`. There is no `0.5` tag.
- **Postgres init script ordering**: our SQL files start at `010_` so Apache AGE's own bundled `00-create-extension-age.sql` runs first. Don't rename our files back to `00X_` or you'll fight a duplicate-extension error.
- **`uv sync --package X --package Y` does not work**. Use `uv sync --all-packages` or one `--package` at a time.
- **Storybook 8 + Next 15.5**: incompatible (`@storybook/nextjs` chokes on a webpack hook). We use `@storybook/react-vite` with tiny `next/link` + `next/navigation` mocks in `.storybook/mocks/`.
- **Compose shell-var escaping**: use `$$VAR` inside healthcheck CMD-SHELL strings so the container shell — not docker compose — evaluates the substitution.
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

When you finish implementing a change, the workflow ends with `openspec archive <name>` (consult the OpenSpec skill files in `.claude/skills/openspec-archive-change/` for the full procedure — we haven't archived anything yet, so be careful the first time).

## The architecture explainer

`docs/explainer/index.html` is a single self-contained page that explains every pillar of
the system in plain English, with a clickable end-to-end flow per pillar and the OpenSpec
history that shaped it. Open it by double-clicking — no server, no CDN, no npm.

```bash
make explainer          # rebuild; snapshots a new version only if content changed
make explainer-check    # exit 1 if stale (CI)
make explainer-open     # rebuild and open in a browser
```

How it stays accurate:

- **Per-pillar spec history is derived**, never hand-maintained. Each pillar's
  `capabilities:` frontmatter is joined against the `## Capabilities` tags in every
  `proposal.md`, so archiving a change updates the affected pillars automatically.
- **Hand-authored content lives in `tools/explainer/content/*.md`** — one file per pillar,
  holding only what a machine cannot infer: the plain-English description, the flow
  narrative, and the honest `## Gaps` list. Most changes need no edit here.
- **Edit content when** a change closes a gap, adds a pillar, or alters how a flow works.
  If you add a new capability tag, some pillar must claim it or the build fails loudly.
- **Versions are snapshots.** A build whose content hash differs from the newest snapshot
  writes `docs/explainer/versions/NNNN-YYYY-MM-DD.json` and appends to `index.json`. Every
  snapshot is inlined into the HTML, so the Compare Versions view diffs them offline.
  Re-running with no content change rewrites only `index.html`, so it is idempotent.

The explainer is written from the **verified state of the code**, not the aspiration. It
says ingestion is git-only, the pipeline has no authentication, and the knowledge graph is
not consulted during `/retrieve` — because all three are true. Keep it that way.

## When in doubt

Stop. Ask the user. The OpenSpec workflow exists so the user has a chance to course-correct before code is written. Use it.
