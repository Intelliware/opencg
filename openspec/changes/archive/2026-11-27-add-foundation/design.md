## Context

The reference architecture frames "enterprise context engineering" as a discipline that must be built, tested, and owned independently of any single LLM. Each layer of the pipeline has its own contract, telemetry, and failure mode. openCG implements that pipeline as a self-hostable, open-source, dockerized stack that any AI tool can consume through MCP. Open-source components are preferred; light Anthropic models (Haiku) and local Ollama models are the default backends. The v0 deployment model is **single-tenant per docker-compose stack** — multi-tenant isolation is out of scope.

The reference architecture image (`docs/reference-architecture/`) is the source of truth for the pipeline shape. This document records the implementation decisions that diverge from or refine it.

### High-level shape

```
                                ┌─────────────────────────┐
                                │      MCP CLIENT         │
                                │ (Claude/Cursor/agent)   │
                                └──────────┬──────────────┘
                                           │ MCP (stdio / HTTP)
                                ┌──────────▼──────────────┐
                                │      MCP SERVER (TS)    │   ──▶ OTel
                                └──────────┬──────────────┘
                                           │ correlation_id, identity
              ┌────────────────────────────▼─────────────────────────────┐
              │                  RETRIEVAL PIPELINE                       │
              │  1 identity  → 2 intent → 3 hybrid → 4 catalog/graph     │
              │                → 5 rerank+compress → 6 entitle+audit     │
              │                → 7 return (structured MCP payload)       │
              └──┬──────────────┬─────────────┬─────────────┬────────────┘
                 │ reads        │ reads       │ writes      │ writes
        ┌────────▼──┐ ┌─────────▼─┐ ┌─────────▼──┐ ┌────────▼────────┐
        │  QDRANT   │ │  POSTGRES │ │   VALKEY   │ │   AUDIT LOG     │
        │ (vectors) │ │ (catalog+ │ │ cache/sess │ │ (append-only PG)│
        │           │ │ AGE graph)│ │            │ │                 │
        └─────▲─────┘ └─────▲─────┘ └────────────┘ └─────────────────┘
              │             │
              │ writes      │ writes
       ┌──────┴─────────────┴────────┐        ┌──────────────────────┐
       │   BACKGROUND ENRICHMENT     │◀──────▶│   USAGE FEEDBACK     │
       │ change-driven / freshness / │        │   stream             │
       │ relationship inference /    │        └──────────────────────┘
       │ usage aggregation           │
       └────────┬────────────────────┘
                │ pulls
       ┌────────▼─────────────────────┐
       │   INGESTION CONNECTORS       │
       │   git · confluence · web ·   │
       │   custom-api                 │
       └──────────────────────────────┘

Model adapters (used by stages 2, 3, 5 and enrichment):
   Ollama   |   Anthropic   |   OpenAI-compatible
Policy:    OPA sidecar  (stage 6)
Telemetry: OTel collector → Tempo / Loki / Prometheus / Grafana
```

## Goals / Non-Goals

**Goals:**
- Implement the 7-stage contextual layer pipeline as named, independently testable services.
- Expose the pipeline through MCP so any compliant AI tool can consume it without bespoke integration.
- Make the knowledge catalogue **reviewable**: queries, returned context, vector neighbourhoods, and a named-relationship graph all editable from an admin UI.
- Build observability, token accounting, and an immutable audit log into every stage from day one.
- Default to OSS components and pluggable model providers (Ollama first-class, Anthropic Haiku/Sonnet first-class).
- Bring the entire stack up with a single `docker compose up`.

**Non-Goals:**
- Multi-tenant SaaS isolation in v0. Tenants run separate stacks. The data model carries a `tenant` slug only to keep the door open.
- Real authentication in v0. Identity is stubbed; the propagation contract is set so auth can be added later without touching downstream stages.
- Fine-tuning / training pipelines for embeddings or rerankers — openCG selects pre-trained models via adapters.
- An end-user "ask the LLM" chat UI. We are the context layer, not the consumer.
- Bring-your-own-graph-database. Postgres + Apache AGE is the only graph implementation in v0.

## Decisions

### D1. TypeScript for the MCP server, Python for retrieval pipeline and workers

**Choice**: MCP server in TypeScript (Node, `@modelcontextprotocol/sdk`); retrieval pipeline, ingestion, and background workers in Python (FastAPI / Celery-or-arq).

**Rationale**: TypeScript has the most mature MCP tooling and the smallest surface for a request router. Python is where the embedding/rerank/extractor ecosystem lives (LangChain-style integrations, Qdrant client, AGE driver, sentence-transformers, etc.). Splitting language at the MCP boundary keeps each side in its native ecosystem.

**Alternatives considered**: All-TypeScript (simpler ops, but Python ML ecosystem is materially better for the pipeline internals); all-Python (FastMCP exists but its tooling and IDE integration trail Node's).

### D2. Qdrant over ChromaDB

**Choice**: Qdrant as the vector store.

**Rationale**: Built-in hybrid (dense + sparse) search and RRF fusion, payload filters that push down to the index, snapshot APIs that map cleanly to the recreatability requirement, and better operational ergonomics for a long-lived deployment.

**Alternatives considered**: ChromaDB (matches reference architecture diagram and is simpler, but weaker for hybrid and snapshots); pgvector (would collapse the storage stack to one engine, but loses Qdrant's filter and HNSW performance and forces us into a Postgres-side rerank pipeline that we'd outgrow); Weaviate (good, but heavier and the licence is more complex).

### D3. Apache AGE on Postgres for the graph (not a dedicated graph DB)

**Choice**: Postgres 16 + Apache AGE extension. Lexical fallback uses `pg_trgm` and `tsvector` so the same engine answers BM25-style queries.

**Rationale**: Two engines (Postgres + Qdrant) instead of three. Audit log lives in the same DB as the graph, simplifying transactional guarantees around "promote candidate edge" + "write audit row". AGE supports openCypher, which keeps the graph queries idiomatic.

**Alternatives considered**: Neo4j Community (more mature, better tooling, but adds an engine and its enterprise features are gated); Memgraph (fast, OSS, but smaller ecosystem); embedding the graph in Qdrant payloads (works for trivial traversal but breaks for anything beyond 1 hop).

### D4. Named relationships with a curated vocabulary + candidate review queue

**Choice**: Edges are typed from a curated vocabulary (`depends_on`, `defined_in`, `supersedes`, ...). New edges from auto-extraction land in a `candidate` state with a `confidence` score and `evidence_uri`; they are invisible to retrieval until an admin promotes them. The vocabulary itself is editable through the admin API and audited.

**Rationale**: Auto-extraction at LLM precision will be wrong often enough that surfacing candidates is dangerous. Requiring promotion makes the graph trustworthy. A curated vocabulary keeps semantics legible and prevents extractor drift.

**Alternatives considered**: Free-text relationship labels (cheap to ingest, painful to query and visualize); LLM-classified, auto-promoted edges (fast but degrades the graph quickly); no graph at all and rely on vector neighbourhoods (loses the "what's connected, and how" answer the architecture explicitly calls for).

### D5. DataHub: not the catalog, but a future source connector

**Choice**: Do **not** embed DataHub as the catalog-store. Build the catalog as a small set of Postgres tables. Add a DataHub *source connector* later so orgs already running DataHub can pull dataset metadata in as another knowledge source.

**Rationale**: DataHub's domain model is dataset-centric (tables, columns, dashboards, pipelines). Our entities are documents/concepts/code passages — bolting them onto DataHub's model fights the platform. DataHub's operational footprint (Kafka + Elasticsearch + GMS + frontend) is several times larger than what we need and would dominate the docker-compose stack for a single user. DataHub's UI is for data stewardship, not for inspecting LLM context windows, so we'd build a separate admin UI either way.

**Alternatives considered**: Adopt DataHub as the catalog and build everything else around it (rejected — wrong shape, heavy ops); Amundsen (similar shape problems); OpenMetadata (closer in spirit but same dataset-bias and weight).

### D6. Identity stub now, contract correct

**Choice**: v0 ships with a hardcoded principal and roles loaded from `opencg.yaml`. The MCP server attaches them to every outbound pipeline call and accepts a caller-supplied `x-correlation-id`. OPA evaluates the same identity shape it will evaluate against real JWTs in a later change.

**Rationale**: Auth is the slowest possible thing to get wrong, and we don't want the pipeline contracts to leak from "no identity" to "identity exists". Lock the shape now, plug a real verifier in later without touching stages 3-7.

### D7. Single config file, env-overrideable

**Choice**: A single `opencg.yaml` configures providers, connectors, freshness, audit retention, telemetry endpoints, and entitlement defaults. Environment variables override file values via `OPENCG__<SECTION>__<KEY>` convention.

**Rationale**: Operators consistently report flat ENV + one file as the easiest config to reason about. Avoids the 12-factor purist trap of scattering config across many env vars while keeping CI/CD ergonomic.

### D8. Per-stage token accounting is a first-class span attribute, not a sidecar

**Choice**: Token counts are recorded on the OTel span for the stage that invoked the model, then aggregated into Prometheus counters and into the response envelope. No separate "billing" or "usage" pipeline.

**Rationale**: Token usage is always answered alongside "where was time spent" and "what model ran". Putting it on the same span makes per-request analysis trivial and avoids a parallel observability path that drifts from reality.

### D9. Open-source rerankers via Ollama by default; Cohere stays optional

**Choice**: Default rerank model is `bge-reranker-v2-m3` (or equivalent cross-encoder) served via Ollama or the OpenAI-compatible adapter; the Cohere rerank adapter is shipped as an option but not the default.

**Rationale**: Avoids a hard third-party dependency for the default path; keeps the OSS-first promise; lets organizations swap to Cohere or any hosted reranker through one config change.

### D10. Audit log lives in Postgres with row-level immutability

**Choice**: Audit records are written to a Postgres table with `INSERT` only; a trigger blocks `UPDATE` on all columns except `legal_hold` (which can be set, never cleared via API). Retention is enforced by a partition policy.

**Rationale**: Reuses the storage already present, avoids a separate WORM store, and gives us the recreatability + immutability the SR 26-2 layer requires without operational sprawl.

## Risks / Trade-offs

- **Risk: Auto-extracted relationships overwhelm reviewers** → Mitigation: confidence thresholds tunable per relationship type; review queue paginated and bulk-actionable; periodic auto-archive of low-confidence candidates older than N days.
- **Risk: Token accounting drifts when streaming responses are involved** → Mitigation: finalize spans only on stream end; emit per-chunk events for live dashboards but reconcile counters from the end-of-stream summary.
- **Risk: Ollama models on a developer laptop are too slow for interactive MCP usage** → Mitigation: Anthropic Haiku is a first-class adapter; the default `dev` profile prefers Haiku if `ANTHROPIC_API_KEY` is set, Ollama otherwise.
- **Risk: Audit retention + per-request snapshots balloon storage** → Mitigation: Postgres partitioning by week; configurable retention; Qdrant snapshots only on a schedule, not per request — the audit record references the last snapshot in effect.
- **Risk: Identity stub leaks into production deploys** → Mitigation: services refuse to start in `local-prod` profile if the stub principal is the only configured identity; bright-banner warnings in the admin UI; integration test that asserts this on startup.
- **Risk: OPA cold-start latency in dev** → Mitigation: ship pre-compiled bundle; admin UI surfaces the policy version and last-load time so drift is observable.
- **Risk: Web indexer becomes a vector for ingesting noise/garbage** → Mitigation: allow-list of domains is required at config time; per-domain crawl budgets; a "quarantine" state where new content from a freshly added domain is held until an admin promotes the first page.

## Migration Plan

Greenfield — no migration. The deployment plan is:

1. Bring up the storage layer (Postgres + AGE, Qdrant, Valkey) and verify migrations apply.
2. Bring up OPA with the default `allow_internal_only` policy.
3. Bring up the model providers (Ollama pulled with default models, Anthropic key validated if set).
4. Bring up the pipeline + MCP server; verify `tools/list` and a stub `search` round-trip.
5. Bring up the admin UI; run the smoke test that ingests a known git repo, lists candidate edges, promotes a few, and re-queries.
6. Bring up the OTel stack; verify traces and metrics flow end-to-end.

Rollback for an individual capability is "stop the service, run the down migrations associated with the change". For the foundation change itself, rollback is `docker compose down -v` (development) — there is no prior version to restore.

## Open Questions

- **OQ1**: Do we want a Python or TypeScript SDK for ingestion connectors first? The framework is Python (D1), but a TypeScript connector SDK would let admins write web-indexing rules close to the MCP layer. Defer to the second change.
- **OQ2**: Should the rerank stage be allowed to *re-query* the catalog/graph based on what the cross-encoder learned? Currently it only re-orders. Revisit after we have real query traces.
- **OQ3**: Where does prompt-template management live? The retrieval pipeline emits assembled context; the actual prompt the downstream LLM uses is not openCG's concern in v0. If we later want to ship "prompt packs" for clients, that's a new capability.
- **OQ4**: Per-tenant policy bundles vs. one global OPA bundle. We chose global for v0 (single-tenant deploys); revisit if/when a multi-tenant change is proposed.
- **OQ5**: Choice of sparse encoder for hybrid search — start with BM25 (Qdrant native), revisit SPLADE once we have a corpus to benchmark on.
