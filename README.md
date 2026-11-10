<p align="center">
  <img src="./docs/assets/opencg-logo.png" alt="Open Context Graph logo" width="120" height="120" />
</p>

<h1 align="center">Open Context Graph</h1>

<p align="center">
  <em>Open-source, self-hostable enterprise context layer fabric — exposed as MCP, CLI, and Retrieval API.</em>
</p>

---

Open Context Graph (openCG) is a dockerized set of services that lets a single person or an organization run a private knowledge catalogue and serve it to any AI tool — Claude, Cursor, open-weight models, in-house agents — through a single MCP endpoint. It implements the contextual-layer pipeline (identity → intent → hybrid retrieval → catalog/graph enrichment → rerank + token-budget compression → entitlement → audit) and is built to learn continuously from usage. Open-source components are preferred; local Ollama models are the default embeddings backend, with light hosted chat models reserved for intent and extraction paths.

## Vision

> "If your AI architecture is just your LLM tool RAG-ing against a vector database, you don't have an AI architecture. You have one component."

openCG builds out the missing components: identity, intent, hybrid retrieval, catalog/graph enrichment, rerank + compression, entitlement, audit, continuous enrichment, and an inspection UI. Every stage is independently testable, observable, and replaceable.

## Status

The **thin MVP** — the first end-to-end working slice — is implemented and running in Docker Compose, alongside an admin UI for vector search, entity inspection, ingestion control, and knowledge-graph review. The full v0 vision is broader and is delivered as a series of OpenSpec changes that flow from proposal → design + specs → tasks → implementation → archive.

**Shipped** (archived under [`openspec/changes/archive/`](./openspec/changes/archive/)):

- **`bootstrap-thin-mvp`** — the v0 stack: TS MCP server, four-stage retrieval pipeline, git ingestion CLI, query review page, immutable audit log, local Ollama embeddings, Docker Compose dev profile.
- **`add-admin-vector-and-content`** — admin UI for vector search, entity browse + detail (with tombstone), and ingestion control; pipeline entity/vector endpoints and ingestion proxies; an HTTP surface on ingestion alongside the CLI.
- **`add-knowledge-graph`** — named concept relationships, deterministic code graphs, best-effort text extraction, graph traversal, candidate review, and an editable relationship vocabulary.
- **`adopt-graphifyy`** · **`add-graph-explorer-view`** · **`adopt-shadcn-and-tremor`** · **`default-graph-to-map`** · **`rename-to-opencg`** — code-graph ingestion, the Obsidian-style graph explorer, the shadcn/Tremor admin redesign, and project naming.

**In flight** ([`openspec list`](./openspec/changes/)):

- **[`add-foundation`](./openspec/changes/add-foundation/)** — the **full v0 vision** spanning 12 capabilities (intent classifier, rerank + compress, OPA enforcement, additional connectors, enrichment workers, full admin UI, OTel/Tempo/Grafana stack, …). Each deferred capability ships as its own follow-up change that MODIFIES the requirements earlier changes set.
- **`stabilize-full-smoke`** — deterministic, bounded end-to-end smoke (local fixture + chat stub + OTel verification under a five-minute deadline). _Complete; pending archive._

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
| Observability | OpenTelemetry → compose-local Collector (Tempo/Grafana is a follow-up) |
| Tests | pytest, vitest |
| Deployment | Docker Compose (`dev` profile) |

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
open http://localhost:3000/queries
```

Run the deterministic full-stack verification with `make smoke`. It builds a temporary local Git fixture, uses local embeddings plus an Ollama-compatible chat stub, verifies OTel spans, and enforces a five-minute deadline. A real-provider canary is opt-in via `make smoke-cloud` and is capped at one document and two chunks.

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

Then use `node /absolute/path/to/opencg-fabric/services/mcp-server/dist/index.js` as the command, with env `OPENCG__PIPELINE__URL=http://localhost:8000` and `OPENCG__MCP__PORT=8199` (any free port — it's only the health endpoint).

### Identity

Identity is stubbed in v0 (`local-dev` / roles `admin,reader` / tenant `default`). Override per client with the `OPENCG__IDENTITY__PRINCIPAL`, `OPENCG__IDENTITY__ROLES`, and `OPENCG__TENANT` environment variables.

## Admin UI

| Route | What it does |
|---|---|
| `/queries` | Recent retrievals + audit detail (tokens, fragments, principal, latency) |
| `/vectors` | Search the catalogue by meaning — top-K results with score, source, snippet |
| `/entities` | Filterable, paginated entity browser; click through to detail, lineage, and a tombstone action |
| `/ingestion` | Connector list + last-run summaries; a "Run now" form for git ingests |
| `/graph` | Search concepts, review candidate relationships, inspect evidence, and manage the relationship vocabulary |

Every shared component has a Storybook story neighbour.

## What's in the v0 stack today

- **TypeScript MCP server** (`services/mcp-server`) advertising five tools. `opencg/retrieve_for_context` and `opencg/traverse_graph` are live; the other three return `not_implemented_in_mvp`.
- **Python retrieval pipeline** (`services/pipeline`) with four stages: identity → hybrid retrieval (Qdrant dense + Postgres FTS lexical, fused via RRF) → assemble (token budget + role→classification allow-list) → return.
- **Python ingestion** (`services/ingestion`) with a `opencg-ingest git <url>` CLI: clone, chunk, embed, write Postgres + Qdrant, derive code relationships with graphifyy, and extract candidate text relationships with the configured chat model.
- **Next.js admin UI** (`services/admin-ui`) with query, vector, content, ingestion, and graph-review pages.
- **Storage**: Postgres 16 + Apache AGE for catalog, audit, and the named knowledge graph; Qdrant for vectors; Valkey for cache; compose-internal Ollama for embeddings.
- **Observability**: per-stage OTel spans carrying token attributes; Prometheus counters at `/metrics`; a compose-local OTel Collector that accepts and logs development traces.
- **Immutable audit log** at `opencg.audit_log` (partitioned by week, with a row-level immutability trigger).

**Not in v0:** intent classifier, OPA enforcement, Confluence/custom-API/web connectors, background enrichment workers, the Tempo/Loki/Prometheus/Grafana stack, a `local-prod` compose profile, and real auth.

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
| [`openspec/specs/`](./openspec/specs/) | The archived spec baseline — 10 capability specs |
| [`openspec/changes/add-foundation/`](./openspec/changes/add-foundation/) | The full v0 vision (12 capabilities) |
| [`openspec/changes/archive/2026-06-12-add-knowledge-graph/`](./openspec/changes/archive/2026-06-12-add-knowledge-graph/) | The shipped knowledge-graph contract |
| [`docs/OPERATIONS.md`](./docs/OPERATIONS.md) | Operating the stack — swapping embedding models, env overrides, etc. |

## Credits

Code-side ingestion uses [graphifyy](https://github.com/safishamsi/graphify) (MIT) for AST-level file discovery and symbol extraction across 28 tree-sitter languages. See [`openspec/changes/archive/2026-06-12-adopt-graphifyy/`](./openspec/changes/archive/2026-06-12-adopt-graphifyy/) for the integration contract.

## License

[MIT](./LICENSE), copyright Electric Mind. Third-party components and their licences are listed in [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). See [`CONTRIBUTING.md`](./CONTRIBUTING.md) to get involved and [`SECURITY.md`](./SECURITY.md) to report a vulnerability.
