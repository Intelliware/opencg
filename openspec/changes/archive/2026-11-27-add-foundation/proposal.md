## Why

General-purpose LLMs are trained on general-purpose knowledge. Enterprise standards, taxonomy, patterns, and policies are specific to each organization and never reach the training data. A single LLM tool RAG-ing against a vector database is one component — not an AI architecture.

openCG is an open-source, self-hostable implementation of the reference contextual-layer pipeline. It is a dockerized set of services that exposes an organization's (or individual's) private knowledge to any AI tool — Claude, Cursor, open-weight models, in-house agents — through a single MCP endpoint. Every stage of the pipeline is independently testable and observable; the knowledge catalogue is reviewable and editable (vector neighbourhoods and a named-relationship graph) via an admin UI; and the system learns continuously from usage. Open-source components are preferred; light Anthropic models (Haiku) and local Ollama models are the default model backends.

## What Changes

- New service: **MCP server** (TypeScript) exposing `search`, `retrieve_for_context`, `get_entity`, `traverse_graph`, `submit_feedback` tools and a structured response contract.
- New service: **Retrieval pipeline** — orchestrates the 7-stage runtime path (identity → intent classification → hybrid retrieval → catalog/graph enrichment → rerank+compress → entitlement+audit → structured return).
- New service: **Background enrichment workers** — change-driven enrichment, freshness monitoring, relationship inference, usage-feedback streaming.
- New service: **Ingestion connectors** — git, confluence, custom HTTP APIs, and a web-page indexer with allow-listed domains.
- New service: **Admin UI** — query review, returned-context inspection, graph relationship management, vector neighbourhood exploration, content management, ingestion control.
- New shared storage layer: **PostgreSQL** (Apache AGE for graph, `pg_trgm` and `tsvector` for BM25-style lexical), **Qdrant** (vector store with hybrid dense+sparse), **Valkey** (cache + session), **OPA sidecar** (policy engine).
- New abstraction: **Model-provider adapters** — single interface for embeddings, intent classification, rerank, generation; first-class adapters for Ollama and Anthropic; OpenAI-compatible adapter for portability.
- **Identity stub** — hardcoded principal + correlation ID in v0; auth is explicitly deferred but the propagation contract is established now so it can be swapped without touching downstream stages.
- **Observability built into every stage**: OpenTelemetry traces, Prometheus metrics, and per-stage token accounting (input tokens, output tokens, est. cost, model, latency) on every request, indexed by correlation ID.
- **Audit + recreatability** ("SR 26-2") — every assembled context window is logged with retrieved IDs, applied entitlements, model+prompt versions so any decision can be reconstructed.
- **Docker Compose** stack with `dev` and `local-prod` profiles for one-command bring-up.

## Capabilities

### New Capabilities

- `mcp-server`: TypeScript MCP server exposing tools and resources for AI clients; propagates identity + correlation ID to the pipeline.
- `retrieval-pipeline`: 7-stage runtime orchestrator; per-stage telemetry; deterministic, recreatable output for a given input + state snapshot.
- `knowledge-graph`: Postgres + Apache AGE schema with **named relationship types**, automatic relationship extraction during ingestion/enrichment, and review/edit APIs.
- `catalog-store`: Entity registry — IDs, source lineage, freshness, owner, classification, and metadata used by structured/direct query.
- `vector-index`: Qdrant collections with hybrid dense+sparse search; per-source filtering; deterministic snapshots for audit.
- `ingestion`: Pluggable connector framework with adapters for git repos, Confluence, custom HTTP APIs, and a web indexer (allow-listed domains, robots-respecting).
- `background-enrichment`: Async workers for change-driven enrichment, freshness checks, periodic relationship inference, and continuous usage-feedback ingestion.
- `model-providers`: Provider-agnostic adapter layer for embeddings, intent classification, rerank, and generation; Ollama and Anthropic adapters in v0.
- `entitlement-audit`: OPA-backed entitlement enforcement at assembly time + immutable, append-only audit log that captures every assembled context.
- `observability`: OpenTelemetry traces, Prometheus metrics, and per-stage token accounting tied to correlation IDs and audit records.
- `admin-ui`: Web UI for query review, returned-context inspection, graph relationship CRUD, vector neighbourhood exploration, content management, and ingestion control.
- `deployment`: Docker Compose stack and configuration model for single-tenant deployments.

### Modified Capabilities

None — greenfield project.

## Impact

- Establishes the repository layout: `services/{mcp-server,pipeline,enrichment,ingestion,admin-ui}`, `packages/shared`, `infra/{compose,opa,otel,grafana}`, `docs/`.
- External runtime dependencies: PostgreSQL 16 + Apache AGE, Qdrant, Valkey, OPA, an OpenTelemetry collector (Tempo/Loki/Prometheus/Grafana stack for local), Ollama (optional locally) or Anthropic API key.
- **Identity is stubbed** — v0 is not safe for multi-user production. Hardening auth is a follow-up change.
- **Single-tenant per deploy** — multi-tenant isolation is not in scope; tenants run separate stacks.
- Establishes the model-provider adapter contract; every model swap in future changes happens through this seam.
- Establishes the per-stage token-accounting contract; downstream cost/limit features build on it.
