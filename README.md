<p align="center">
  <img src="./docs/assets/opencg-logo.png" alt="Open Context Graph logo" width="120" height="120" />
</p>

<h1 align="center">Open Context Graph</h1>

<p align="center">
  <em>Open-source, self-hostable enterprise context layer fabric — exposed as MCP, CLI, and Retrieval API.</em>
</p>

<p align="center">
  <a href="https://github.com/Intelliware/opencg/actions/workflows/ci.yml"><img src="https://github.com/Intelliware/opencg/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT licence" /></a>
</p>

---

Open Context Graph (openCG) is a dockerized set of services that lets a single person or an organization run a private knowledge catalogue and serve it to any AI tool — Claude, Cursor, open-weight models, in-house agents — through a single MCP endpoint. It implements the contextual-layer pipeline (identity → intent → hybrid retrieval → catalog/graph enrichment → rerank + token-budget compression → entitlement → audit) and is built to learn continuously from usage. Open-source components are preferred; local Ollama models are the default embeddings backend, with light hosted chat models reserved for intent and extraction paths.

## Vision

> "If your AI architecture is just your LLM tool RAG-ing against a vector database, you don't have an AI architecture. You have one component."

openCG builds out the missing components: identity, intent, hybrid retrieval, catalog/graph enrichment, rerank + compression, entitlement, audit, continuous enrichment, and an inspection UI. Every stage is independently testable, observable, and replaceable.

## Status

**Version 0.1.0, released 2026-11-10**: the first public release, prepared by [`prepare-open-source-release`](./openspec/changes/archive/2026-11-10-prepare-open-source-release/). Release notes are in [`CHANGELOG.md`](./CHANGELOG.md) and on the [releases page](https://github.com/Intelliware/opencg/releases).

The thin MVP, the first end-to-end working slice, runs in Docker Compose, with an admin UI for vector search, entity inspection, ingestion control and knowledge-graph review. The full v0 vision is broader and is delivered as a series of OpenSpec changes, each going proposal, then design and specs, then tasks, implementation and archive.

**Shipped** (archived under [`openspec/changes/archive/`](./openspec/changes/archive/)), with the date each was archived:

| Date | Change | What it delivered |
|---|---|---|
| 2026-06-12 | `add-admin-vector-and-content` | Admin UI vector search, entity browse and detail (with tombstone), ingestion control; pipeline entity, vector and ingestion-proxy endpoints; an HTTP API on ingestion |
| 2026-06-12 | `add-knowledge-graph` | Named concept relationships, deterministic code graphs, best-effort text extraction, traversal, candidate review, editable vocabulary |
| 2026-06-12 | `adopt-graphifyy` | AST-level code discovery and symbol chunks via graphifyy |
| 2026-06-14 | `add-graph-explorer-view` · `adopt-shadcn-and-tremor` | Interactive graph map; shadcn/Tremor redesign with light and dark themes |
| 2026-06-15 | `default-graph-to-map` · `rename-to-cortex` | Map as the default graph view; interim project name |
| 2026-06-16 | `fix-code-graph-filename-leak` | Real source paths in code-graph names and symbol IDs |
| 2026-06-17 | `add-mcp-http-transport` · `reorder-admin-nav` · `stabilize-full-smoke` · `update-graph-map-detail` | Remote MCP over HTTP; nav order; the deterministic, bounded smoke test; map search and detail panel |
| 2026-06-18 | `add-mcp-oauth-stopgap` · `rename-to-open-context-graph` | OAuth stopgap for claude.ai connectors; the final name, Open Context Graph |
| 2026-11-10 | `exclude-tombstoned-from-retrieval` | Tombstoned entities no longer returned by retrieval or vector search |
| 2026-11-10 | `prepare-open-source-release` | The v0.1.0 release work: fresh-clone fixes, loopback-only defaults, an optional admin login, ingestion URL validation, the Playwright e2e suite, CI, branch protection, and community files |
| 2026-11-10 | `bootstrap-thin-mvp` | The v0 stack contract: MCP server, retrieval pipeline, git ingestion, audit log, compose. Archived as superseded; its open items are recorded against later changes |

**In flight** ([`openspec list`](./openspec/changes/)):

- **[`add-foundation`](./openspec/changes/add-foundation/)** is the **full v0 vision**, spanning 12 capabilities: intent classifier, rerank and compression, OPA enforcement, more connectors, enrichment workers, the Tempo/Grafana stack, and more. Each deferred capability ships as its own follow-up change that modifies the requirements earlier changes set.

## Stack

| Concern | Choice |
|---|---|
| Monorepo | `pnpm` + `uv` workspaces |
| MCP server | TypeScript (`@modelcontextprotocol/sdk`) |
| Pipeline · ingestion · workers | Python 3.12 (FastAPI, asyncpg, httpx) |
| Vector store | Qdrant (dense + lexical fusion) |
| Catalog · audit · graph | PostgreSQL 16 + Apache AGE |
| Cache | Valkey |
| Embeddings | Ollama (`nomic-embed-text`, compose-internal) |
| Chat / extraction | Ollama Cloud (`gemma3:4b` default) |
| Admin UI | Next.js 15 (App Router) + Storybook |
| Observability | OpenTelemetry → Collector → Tempo, Prometheus, Grafana (opt-in: `make up-obs`); `/metrics` on every service |
| Tests | pytest, vitest, Playwright (admin UI end-to-end), a deterministic smoke script |
| Deployment | Docker Compose (`dev` profile; smoke and e2e overlays for tests) |
| CI | GitHub Actions: `static`, `dependency-review`, full-stack `stack`, `observability`; Dependabot |

## Quickstart

```bash
# 1. Bring up the stack (postgres+AGE, qdrant, valkey, ollama, pipeline,
#    mcp-server, ingestion, admin-ui). First start pulls images + the embedding model.
cp .env.example .env
make up-d

# 2. Ingest a public git repo
make ingest-git REPO=https://github.com/anthropics/anthropic-cookbook

# 3. Retrieve context directly from the pipeline
curl -sS -X POST http://localhost:8000/retrieve \
  -H 'content-type: application/json' \
  -d '{
    "correlation_id":"hello-001",
    "identity":{"principal":"local-dev","roles":["admin","reader"],"tenant":"default"},
    "tool":"retrieve_for_context",
    "query":"how do I do prompt caching",
    "token_budget":2000
  }' | jq

# 4. Open the admin UI
open http://localhost:3000
```

**Optional: observability.** Prometheus, Tempo and Grafana are not part of the default stack. To add them (about 700 MB more RAM), run:

```bash
make up-obs                    # the dev stack plus the observability overlay
open http://localhost:3030     # Grafana: sign in as admin / admin (set OPENCG__GRAFANA__ADMIN_PASSWORD)
make down                      # stops everything, overlay included
```

Grafana opens on six "openCG" dashboards (requests, stages, tokens and cost, ingestion, audit, providers), and Tempo finds any MCP call by its `correlation_id`. Without the overlay every service still serves `/metrics` and the collector still logs spans. See [`docs/OPERATIONS.md`](./docs/OPERATIONS.md#observability).

Every port binds to `127.0.0.1` and can be moved in `.env` if it collides with something already running (see [`docs/OPERATIONS.md`](./docs/OPERATIONS.md#network-exposure-and-host-ports)). To work on the code, start with [`CONTRIBUTING.md`](./CONTRIBUTING.md) and `make bootstrap`.

Run the deterministic full-stack verification with `make smoke`. It builds a temporary local Git fixture, uses local embeddings plus an Ollama-compatible chat stub, verifies OTel spans and every service's `/metrics`, and enforces a five-minute deadline. `make smoke-obs` runs it with the optional observability overlay and also checks Prometheus, Tempo and Grafana. A real-provider canary is opt-in via `make smoke-cloud` and is capped at one document and two chunks.

## Connect your AI tools (MCP)

With the stack running (`make up-d`), openCG exposes its catalogue over the **Model Context Protocol** via the `opencg` MCP server — over **stdio** (spawn it as a subprocess) or a **remote HTTP** endpoint (connect by URL). Two tools are live today — `opencg/retrieve_for_context` (hybrid retrieval) and `opencg/traverse_graph` (walk the knowledge graph); the other three return `not_implemented_in_mvp`. Any MCP-capable client can connect.

The portable way to launch it spawns the **already-built compose image** on openCG's Docker network — no local Node, build, or absolute paths required:

```bash
docker run -i --rm --network opencg_default \
  -e OPENCG__PIPELINE__URL=http://pipeline:8000 \
  opencg/mcp-server:local
```

> It only works while the stack is up — the server reaches the pipeline over the `opencg_default` Docker network (the compose project is named `opencg`, so the network name is stable). Stack down → the client shows a connection error.

### Claude Code

```bash
claude mcp add opencg -- \
  docker run -i --rm --network opencg_default \
  -e OPENCG__PIPELINE__URL=http://pipeline:8000 opencg/mcp-server:local
```

Append `--scope user` to make it available in every project. Verify with `claude mcp get opencg` (expect `✓ Connected`), then ask, e.g., *"use opencg to find what the catalogue says about core banking."*

### Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows: `%APPDATA%\Claude\claude_desktop_config.json`), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "opencg": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "opencg_default",
               "-e", "OPENCG__PIPELINE__URL=http://pipeline:8000",
               "opencg/mcp-server:local"]
    }
  }
}
```

### Cursor

Add the same entry to `.cursor/mcp.json` (this project) or `~/.cursor/mcp.json` (all projects), then reload Cursor — it uses the identical `mcpServers` schema:

```json
{
  "mcpServers": {
    "opencg": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "opencg_default",
               "-e", "OPENCG__PIPELINE__URL=http://pipeline:8000",
               "opencg/mcp-server:local"]
    }
  }
}
```

### Remote connection over HTTP (connect by URL)

The server also speaks the **Streamable HTTP** transport at `http://localhost:8181/mcp` (the same port as the health checks) — so clients connect by **URL** with no subprocess, and it's reachable across the network once you expose the port (e.g. a tunnel).

> **Set a token before exposing it.** With `OPENCG__MCP__HTTP_TOKEN` unset, `/mcp` is open (fine on loopback — the server logs an "unauthenticated" warning). Set it in `.env` and pass it as a bearer header to require auth.

Claude Code:

```bash
claude mcp add --transport http opencg http://localhost:8181/mcp \
  --header "Authorization: Bearer $OPENCG__MCP__HTTP_TOKEN"
```

(Drop `--header` when no token is set.) Cursor and Claude Desktop use the `url` form:

```json
{
  "mcpServers": {
    "opencg": {
      "url": "http://localhost:8181/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

### Connect from claude.ai (OAuth — stopgap)

claude.ai and Claude Desktop's "Add custom connector" GUI authenticate via **OAuth**, not a bearer header. The MCP server ships a **temporary, minimal** OAuth server (single shared password, in-memory tokens — see `services/mcp-server/src/oauth.ts`, marked `REPLACE-BEFORE-PROD`). Enable it by setting both:

```bash
OPENCG__MCP__PUBLIC_URL=https://your-host.ngrok.app   # externally reachable base URL
OPENCG__MCP__OAUTH_PASSWORD=<a shared access password>
```

Restart the mcp-server, then in claude.ai: **Settings → Connectors → Add custom connector** → URL `https://your-host.ngrok.app/mcp`. Claude runs the OAuth flow; on the consent screen, enter the access password. (The static `OPENCG__MCP__HTTP_TOKEN` keeps working alongside this for Claude Code / Cursor.)

> This OAuth is a stopgap, not production auth: one shared password (no per-user identity), tokens are in-memory (lost on restart), self-issued. Replace with a real identity provider before any real deployment.

### Run on the host instead of Docker

To avoid a container per session, build the server once and point it at the host-exposed pipeline:

```bash
pnpm install && pnpm --filter @opencg/mcp-server build
```

Then use `node /absolute/path/to/opencg/services/mcp-server/dist/index.js` as the command, with env `OPENCG__PIPELINE__URL=http://localhost:8000` and `OPENCG__MCP__PORT=8199` (any free port — it's only the health endpoint).

### Identity

Identity is stubbed in v0 (`local-dev` / roles `admin,reader` / tenant `default`). Override per client with the `OPENCG__IDENTITY__PRINCIPAL`, `OPENCG__IDENTITY__ROLES`, and `OPENCG__TENANT` environment variables.

## Admin UI

| Route | What it does |
|---|---|
| `/` | Overview dashboard: recent queries, entity and candidate-edge counts, connectors, top sources |
| `/queries` | Recent retrievals + audit detail (tokens, fragments, principal, latency) |
| `/vectors` | Search the catalogue by meaning — top-K results with score, source, snippet |
| `/entities` | Filterable, paginated entity browser; click through to detail, lineage, and a tombstone action |
| `/ingestion` | Connector list + last-run summaries; a "Run now" form for git ingests |
| `/graph` | Map (interactive graph with concept search and a detail panel), Concepts, Candidate review, and Vocabulary tabs |
| `/login` | Sign-in, used only when `OPENCG__ADMIN_UI__PASSWORD` is set (the optional access gate) |

Without a password the UI shows an "Unauthenticated mode" banner on every page; see [`docs/OPERATIONS.md`](./docs/OPERATIONS.md#admin-ui-access-gate).

Every shared component has a Storybook story neighbour.

## What's in the v0 stack today

- **TypeScript MCP server** (`services/mcp-server`) advertising five tools. `opencg/retrieve_for_context` and `opencg/traverse_graph` are live; the other three return `not_implemented_in_mvp`.
- **Python retrieval pipeline** (`services/pipeline`) with four stages: identity → hybrid retrieval (Qdrant dense + Postgres FTS lexical, fused via RRF) → assemble (token budget + role→classification allow-list) → return.
- **Python ingestion** (`services/ingestion`) with a `opencg-ingest git <url>` CLI: clone, chunk, embed, write Postgres + Qdrant, derive code relationships with graphifyy, and extract candidate text relationships with the configured chat model.
- **Next.js admin UI** (`services/admin-ui`) with query, vector, content, ingestion, and graph-review pages.
- **Storage**: Postgres 16 + Apache AGE for catalog, audit, and the named knowledge graph; Qdrant for vectors; Valkey for cache; compose-internal Ollama for embeddings.
- **Observability**: one OTel trace per MCP tool call across the MCP server and pipeline, with `correlation_id` on every span and a child span per model call; `/metrics` on the pipeline, ingestion and MCP server; token usage and estimated cost per provider in every usage envelope, audit row and admin UI view; a compose-local OTel Collector. Prometheus, Tempo and Grafana with six dashboards are an opt-in overlay (`make up-obs`).
- **Immutable audit log** at `opencg.audit_log` (range-partitioned on `created_at`, with a row-level immutability trigger).

**Not in v0:** intent classifier, OPA enforcement, Confluence/custom-API/web connectors, background enrichment workers, log aggregation (Loki, planned as `add-log-aggregation`), alerting, a `local-prod` compose profile, and real auth.

## API reference

Host ports below are the defaults; all of them can be moved in `.env`. None of these HTTP APIs authenticate callers except `/mcp` and the admin UI (see [`SECURITY.md`](./SECURITY.md)).

### Pipeline (`http://localhost:8000`)

| Method and path | Purpose |
|---|---|
| `GET /healthz` · `GET /readyz` | Liveness; readiness of Postgres and Qdrant, plus the active embedding model and vector size |
| `GET /metrics` | Prometheus metrics, including `opencg_tokens_total{stage,model,provider,tenant,direction}` |
| `POST /retrieve` | Run the retrieval pipeline for `{correlation_id, identity, tool, query, top_k?, token_budget?}`; returns fragments, a per-stage `usage` envelope and the context hash; writes one audit row |
| `GET /audit/recent?limit=` · `GET /audit/{id}` | Recent retrieval audit rows; one full audit record |
| `GET /entities?source=&classification=&freshness_state=&limit=&offset=` | Paginated entity list, newest first |
| `GET /entities/{id}` | One entity with body, metadata, lineage (parent and chunks) and recent audit appearances |
| `DELETE /entities/{id}` | Tombstone (soft delete; idempotent) |
| `POST /search/vector` | Admin vector search `{query, top_k ≤ 100, filters?}`; no audit row; tombstoned entities excluded |
| `GET /ingestion/connectors` · `POST /ingestion/git/run` · `GET /ingestion/runs/recent` | Proxies to the ingestion service |
| `GET /graph/vocab` · `POST /graph/vocab` · `PATCH /graph/vocab/{name}` · `POST /graph/vocab/{name}/deprecate` | Relationship vocabulary |
| `GET /graph/concepts?state=&search=&limit=&offset=` · `GET /graph/concepts/{id}` | Concept list and search; one concept with confirmed and candidate neighbours |
| `POST /graph/concepts/{id}/promote` · `/demote` · `PATCH` · `DELETE /graph/concepts/{id}` · `POST /graph/concepts/merge` | Concept review: confirm, back to candidate, edit, tombstone, merge |
| `GET /graph/edges?state=&type=&limit=&offset=` | Relationship edges by state (tombstoned edges are never listed), ordered by confidence |
| `POST /graph/edges/{id}/promote` · `/demote` · `PATCH` · `DELETE /graph/edges/{id}` | Edge review; `DELETE` tombstones |
| `GET /graph/traverse?concept_id=&depth=&types=&limit=&include_candidates=` | Neighbourhood traversal (depth 1–4, default 2; the map offers 1–3) |

Every graph write accepts an optional `{"reason": "…"}` and records a row in `opencg.graph_audit_log`.

### Ingestion service (`http://localhost:8100`)

| Method and path | Purpose |
|---|---|
| `GET /healthz` · `GET /readyz` | Liveness and readiness |
| `GET /connectors` | Available connectors (`git` supported; Confluence, custom API and web deferred) |
| `POST /run/git` | Start a git ingest `{repo_url}` in the background; the URL is validated first (see business rules) |
| `GET /runs/recent` | In-memory run history (cleared on restart) |

The CLI inside the container (`python -m opencg_ingestion.cli git <url>` / `re-extract`) offers the same ingest plus re-extraction, without the URL restrictions.

### MCP server (`http://localhost:8181`, or stdio)

| Endpoint | Purpose |
|---|---|
| `/mcp` | Streamable HTTP MCP transport; bearer token and/or OAuth when configured |
| `GET /healthz` · `GET /readyz` | Liveness; readiness of the pipeline |
| `/authorize`, `/token`, `/register`, `/.well-known/oauth-*`, `POST /oauth/approve` | OAuth stopgap, mounted only when `OPENCG__MCP__OAUTH_PASSWORD` and `OPENCG__MCP__PUBLIC_URL` are set |

Tools: `opencg/retrieve_for_context` and `opencg/traverse_graph` are live; `opencg/search`, `opencg/get_entity` and `opencg/submit_feedback` return `not_implemented_in_mvp`.

### Admin UI routes (`http://localhost:3000`)

Browser code never calls the pipeline directly. It goes through same-origin Next route handlers: `/api/proxy/search/vector`, `/api/proxy/entities/{id}`, `/api/proxy/ingestion/git/run` and `/api/proxy/graph/**`. Also served: `/api/healthz` (pipeline-independent liveness) and `/api/auth/login` and `/api/auth/logout` (the access gate).

## Data model

### PostgreSQL 16 + Apache AGE (`infra/postgres/init/`)

The init scripts run once, when the Postgres volume is first created, in file order: `010_extensions`, `020_catalog`, `030_audit`, `040_graph`, `050_graph_audit`, `090_grants`. They start at `010_` so Apache AGE's bundled `00-create-extension-age.sql` runs first. There is no migration framework yet. A schema change means a new numbered file, and existing volumes need `make down-v` or a hand-applied script.

Extensions: `age`, `pg_trgm`, `unaccent`, `uuid-ossp`. An AGE graph named `opencg` holds a `Concept` vertex label and one edge label per vocabulary name. All tables live in the `opencg` schema, and every grant goes to the configured application role (`OPENCG__POSTGRES__USER`).

**`opencg.entity`**: the catalogue. One row per document (parent) and per chunk.

| Column | Type | Notes |
|---|---|---|
| `entity_id` | `uuid` PK | Stable: derived from tenant and `source_uri` (chunks from the parent and chunk or symbol ID) |
| `tenant` · `source` · `source_uri` | `text` not null | Unique together (`entity_source_uri_uq`); chunk URIs carry `#chunk=N` or `#symbol=<id>` |
| `source_revision` | `text` | For example the git commit |
| `parent_entity_id` | `uuid` → `entity`, on delete cascade | Null for documents |
| `title` · `body` | `text` (`body` not null) | Raw text, kept for replay and the admin UI |
| `content_hash` | `text` not null | |
| `classification` | `text`, default `internal` | Filtered by the role allow-list at assembly |
| `owner` | `text` | |
| `metadata` | `jsonb`, default `{}` | For example `chunk_index`, `symbol_id` |
| `freshness_state` | `text`, default `fresh` | `fresh`, `stale` or `unknown` |
| `created_at` · `updated_at` · `ingested_at` · `last_verified_at` | `timestamptz` | |
| `tombstoned_at` | `timestamptz` | Soft delete; cleared by re-ingest |

Indexes: `(tenant, classification)`, `(tenant, freshness_state)`, trigram GIN on `body` and `title`, and full-text GIN on `title || body` (the lexical retrieval leg).

**`opencg.audit_log`**: one row per retrieval. It is range-partitioned on `created_at`; today only the `audit_log_default` partition exists, and weekly partitions are planned. The primary key is `(id, created_at)`. Columns: `correlation_id`, `tenant`, `principal`, `roles text[]`, `tool`, `query`, `intent_plan`, `retriever_versions`, `model_versions` (`jsonb`), `vector_collection`, `vector_snapshot_id`, `candidate_ids uuid[]`, `candidate_decisions jsonb`, `final_entity_ids uuid[]`, `final_context_hash`, `tokens_in`, `tokens_out`, `latency_ms`, `outcome` (`ok` or `error`), `error_code`, `legal_hold boolean`. The trigger `audit_log_no_update` rejects every `DELETE`, and every `UPDATE` except setting `legal_hold`, which can never be cleared once set. Indexes: `correlation_id`; `(principal, created_at desc)`; `(tenant, created_at desc)`.

**`opencg.relationship_vocab`**: relationship types. Columns: `name` PK (`^[a-z][a-z0-9_]*$`), `description`, `inverse`, `directed`, `deprecated_at`, `created_at`. Ten are seeded:
- semantic: `depends_on`, `defined_in`, `supersedes`, `mentions`, `related_to` (undirected), `causes`, `derived_from`;
- code: `calls`, `imports`, `uses`.

**`opencg.concept`**: graph nodes. Columns: `concept_id` PK, `tenant`, `name`, `dedupe_key` (unique per tenant), `description`, `aliases text[]`, `state`, `confidence`, `extractor_version`, `symbol_id`, `symbol_kind`, `source_entity_id`, `created_at`, `updated_at`, `tombstoned_at`. `state` is `candidate`, `confirmed` or `tombstoned`. Indexes: `(tenant, state)`; `(tenant, symbol_id)` where set.

**`opencg.relationship_edge`**: graph edges. Columns: `edge_id` PK, `tenant`, `type` (→ `relationship_vocab.name`), `from_concept_id`, `to_concept_id` (→ `concept`), `state` (the same three values), `confidence`, `extractor_version`, `created_at`, `updated_at`, `tombstoned_at`. `(tenant, from, type, to)` is unique. Indexes: `(state, confidence desc)`, `from_concept_id`, `to_concept_id`.

**`opencg.relationship_evidence`**: which chunks support an edge. Columns: `evidence_id` bigserial PK, `edge_id` (→ `relationship_edge`, on delete cascade), `entity_id` (→ `entity`), `span`, `extractor_version`, `confidence`, `created_at`. Indexes: `edge_id`, `entity_id`.

**`opencg.graph_audit_log`**: every graph state change. Columns: `id`, `created_at`, `actor`, `tenant`, `target_kind` (`concept`, `edge` or `vocab`), `target_id`, `from_state`, `to_state`, `reason`, `before` and `after` (`jsonb`). The trigger `graph_audit_log_no_modify` rejects every `UPDATE` and `DELETE`. Indexes: `(target_id, created_at desc)`, `(actor, created_at desc)`, `(tenant, created_at desc)`.

### Qdrant

One collection per source, named `<collection_prefix><source>` (default `default__git`), with `vector_size` 768 and cosine distance (`opencg.yaml`). Point IDs are chunk `entity_id`s. The payload holds `tenant`, `entity_id`, `parent_entity_id`, `source`, `source_uri` (the parent document's URI), `title`, `text`, `classification`, `chunk_index`, and `symbol_id` for code chunks. Postgres remains the source of truth: tombstones are applied at query time, not written to Qdrant.

### Valkey

Provisioned for caching, unused in v0.

## Key business rules

- **Retrieval.** The dense (Qdrant) and lexical (Postgres full-text) legs run in parallel and are fused by reciprocal rank fusion. Assembly keeps candidates whose `classification` the caller's roles allow (`admin` and `reader`: `internal`, `public`; `public`: `public`; no matching role: `public` only), within the token budget. Every retrieval writes one audit row.
- **Tombstones** are soft and idempotent; the original timestamp is kept. A tombstoned entity is excluded from both retrieval legs and from vector search, while its Qdrant point stays. Re-ingesting the source clears the tombstone. Tombstoning does not cascade to chunks.
- **Ingestion is idempotent.** Stable `uuid5` IDs mean re-ingesting unchanged content updates rows in place instead of duplicating them. Code files become one chunk per AST symbol (via graphifyy); text files are split into paragraph chunks.
- **Graph states.** graphifyy code relationships are written `confirmed`. Relationships extracted from text are `candidate` until an operator promotes them, and those below `OPENCG__PROVIDERS__EXTRACTION__MIN_CONFIDENCE` (0.6) or with an unknown type are dropped. Extraction is best-effort: failures are logged and counted and never fail an ingest.
- **Audit logs are append-only.** Database triggers enforce it; corrections are new rows.
- **Token accounting.** Every model call records its tokens on the OTel span and in `opencg_tokens_total`.
- **"Run now" URL guard.** URLs must be `https`, `ssh`, `git` or `user@host:path`, and must resolve to public addresses unless listed in `OPENCG__INGESTION__GIT__ALLOWED_HOSTS`. They may not embed a password, start with `-`, or use `ext::` or `file://`. Local paths are allowed only under `OPENCG__INGESTION__GIT__LOCAL_ROOTS`.

## Running the tests

| Tier | Command | Needs the stack |
|---|---|---|
| Lint, type-check, unit tests, Storybook build | `make lint`, `make typecheck`, `make test`, `make storybook` (or `make ci-static` for all of them) | no |
| Smoke (deterministic end-to-end) | `make smoke` | yes |
| Observability smoke (optional overlay: Prometheus, Tempo, Grafana) | `make smoke-obs` | yes, with `make up-obs` |
| Admin UI end-to-end (Playwright, Chromium) | `make e2e` (`make e2e-ui` for UI mode) | started if needed |
| Everything CI runs | `make ci` | yes |

CI runs `static` and `dependency-review` on every pull request, and the full-stack `stack` job (smoke plus e2e) on pull requests into `main`, nightly, and on demand. The `observability` job (`make smoke-obs`) runs on every pull request into `main`, on pushes to `main` and nightly, in parallel with `stack`. [`CONTRIBUTING.md`](./CONTRIBUTING.md#tests) explains each tier and how the e2e suite isolates its data.

## Known issues

- **Intermittent hydration error.** About 1 in 100 production page loads logs React error #418, most often on `/entities`. The page recovers on its own. The e2e suite retries once and annotates the report ([#2](https://github.com/Intelliware/opencg/issues/2)).
- **Audit partitioning is planned, not active.** Every audit row lands in the default partition until weekly partitions are pre-created.
- **No schema migrations.** Changing an init script needs a fresh volume (`make down-v`).
- **Run history is in memory.** The ingestion run list clears when the service restarts.
- **Moderate and low dependency advisories** remain, each needing a major-version upgrade. They are listed with their exposure in [`SECURITY.md`](./SECURITY.md#dependency-advisories).
- **v0 has no real authentication.** The known stopgaps are listed in [`SECURITY.md`](./SECURITY.md#deployment-model-and-known-stopgaps).

## OpenSpec is the contract

**Every feature, deviation, or course-correction goes through the OpenSpec change workflow before code is written.** New work starts with `openspec new change <name>`, then proposal → design + specs → tasks → strict validation, then implementation phase by phase. Inline annotations in another change or undocumented pivots are not acceptable.

```bash
openspec list                                  # changes in flight
openspec list --specs                          # the archived spec baseline
openspec show add-foundation                   # the full v0 vision
openspec validate add-foundation --strict      # re-validate
```

## Where to read

| Document | What's there |
|---|---|
| [`openspec/project.md`](./openspec/project.md) | Vision, stack, conventions |
| [`openspec/specs/`](./openspec/specs/) | The archived spec baseline: 12 capability specs |
| [`openspec/changes/add-foundation/`](./openspec/changes/add-foundation/) | The full v0 vision (12 capabilities) |
| [`openspec/changes/archive/2026-06-12-add-knowledge-graph/`](./openspec/changes/archive/2026-06-12-add-knowledge-graph/) | The shipped knowledge-graph contract |
| [`docs/OPERATIONS.md`](./docs/OPERATIONS.md) | Operating the stack: ports and network exposure, the admin gate, ingestion, test overlays, swapping embedding models, troubleshooting |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Setup, the OpenSpec workflow, the test tiers, PR expectations |
| [`SECURITY.md`](./SECURITY.md) | Reporting vulnerabilities, known stopgaps, remaining advisories |
| [`CHANGELOG.md`](./CHANGELOG.md) | Release notes |

## Credits

Code-side ingestion uses [graphifyy](https://github.com/safishamsi/graphify) (MIT) for AST-level file discovery and symbol extraction across 28 tree-sitter languages. See [`openspec/changes/archive/2026-06-12-adopt-graphifyy/`](./openspec/changes/archive/2026-06-12-adopt-graphifyy/) for the integration contract.

## License

[MIT](./LICENSE), copyright Electric Mind. Third-party components and their licences are listed in [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). See [`CONTRIBUTING.md`](./CONTRIBUTING.md) to get involved and [`SECURITY.md`](./SECURITY.md) to report a vulnerability.
