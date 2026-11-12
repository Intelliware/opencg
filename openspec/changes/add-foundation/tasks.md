## Implementation strategy

**The thin-MVP subset has been split out into its own OpenSpec change: [`bootstrap-thin-mvp`](../archive/2026-11-10-bootstrap-thin-mvp/proposal.md).** That change is the authoritative contract for the first end-to-end working slice. This `add-foundation` change remains the canonical record of the full v0 vision; the deferred capability subsets it describes (full knowledge graph, intent classifier, rerank+compress, OPA enforcement, additional connectors, enrichment workers, full admin UI, OTel/Grafana stack, `local-prod` profile) will each be picked up by their own follow-up changes that MODIFY the requirements `bootstrap-thin-mvp` set.

## 1. Repository scaffolding

- [ ] 1.1 Create monorepo layout: `services/{mcp-server,pipeline,enrichment,ingestion,admin-ui}`, `packages/shared`, `infra/{compose,opa,otel,grafana,postgres}`, `docs/`
- [ ] 1.2 Add root `package.json` (workspaces) and `pnpm-workspace.yaml` for TypeScript services
- [ ] 1.3 Add root `pyproject.toml` with `uv` workspace and per-service `pyproject.toml` files for Python services
- [ ] 1.4 Add `Makefile` with `bootstrap`, `up`, `up-dev`, `down`, `test`, `lint`, `format`, `migrate`, `seed`, `smoke` targets
- [ ] 1.5 Add `.editorconfig`, `.gitignore`, `.dockerignore`, root `.env.example`
- [ ] 1.6 Add `opencg.yaml` default config with the schema from D7 and an example commented out

## 2. Storage layer

- [ ] 2.1 Postgres image based on `postgres:16` with Apache AGE compiled in (custom Dockerfile in `infra/postgres/`)
- [ ] 2.2 Initial migration: catalog tables (`entity`, `entity_lineage`, `freshness`), graph vocabulary (`relationship_vocab`), audit (`audit_log` partitioned by week, immutability trigger), usage signals
- [ ] 2.3 AGE schema bootstrap: create graph `opencg`, add label types per relationship vocabulary
- [ ] 2.4 Qdrant compose service with persistent volume; bootstrap script that creates `<tenant>__<source>` collections with dense + sparse vector params
- [ ] 2.5 Valkey compose service with persistent volume
- [ ] 2.6 OPA compose service mounting `infra/opa/policies/` with a default `allow_internal_only` policy and a `health` rule → delivered by `add-identity-and-opa`

## 3. Shared packages

- [ ] 3.1 `packages/shared` (TS) — types for `RetrievalRequest`, `RetrievalResponse`, `IdentityContext`, `AuditRecord`, `IngestEvent`
- [ ] 3.2 `packages/shared-py` (Python) — Pydantic models mirroring the TS types, generated from a single JSON Schema where possible
- [ ] 3.3 Shared OTel bootstrap module per language (resource attrs, exporter wiring, correlation-id propagation helpers)
- [ ] 3.4 Shared config loader (YAML + env-override) per language with validation against `opencg.yaml` schema

## 4. MCP server (TypeScript)

- [ ] 4.1 Scaffold service with `@modelcontextprotocol/sdk` and HTTP transport
- [ ] 4.2 Implement `tools/list` with the five tool schemas (`search`, `retrieve_for_context`, `get_entity`, `traverse_graph`, `submit_feedback`)
- [ ] 4.3 Implement identity stub: load principal/roles from config; accept `x-correlation-id`; generate one when absent → delivered by `add-identity-and-opa`
- [ ] 4.4 Implement pipeline client (HTTP to retrieval-pipeline service); attach identity + correlation ID
- [ ] 4.5 Wire OTel root span per request with the required attributes and `usage` aggregation
- [ ] 4.6 Implement `submit_feedback` — write to feedback stream (Valkey stream)
- [ ] 4.7 `/healthz`, `/readyz` (pipeline reachable + OPA reachable)
- [ ] 4.8 Unit tests for tool schemas, identity propagation, correlation-id behaviour
- [ ] 4.9 Integration test: `tools/list` and a stubbed `retrieve_for_context` round-trip

## 5. Retrieval pipeline (Python)

- [ ] 5.1 FastAPI app with a single `/retrieve` endpoint
- [ ] 5.2 Stage 1 (Identity): validate identity envelope; attach to context → delivered by `add-identity-and-opa`
- [ ] 5.3 Stage 2 (Intent classification): adapter call → `RetrievalPlan`; skip-rule support
- [ ] 5.4 Stage 3 (Hybrid retrieval): Qdrant hybrid query (dense+sparse) with RRF; concurrent dense+lexical paths; configurable weights
- [ ] 5.5 Stage 4 (Catalog/graph lookup): enrich candidates with catalog metadata; resolve 1-hop graph context per candidate
- [ ] 5.6 Stage 5 (Rerank + compress): cross-encoder rerank via adapter; token-budget-aware compression that drops whole documents preferentially
- [ ] 5.7 Stage 6 (Entitle + audit): OPA evaluation per candidate; write audit row with full record → delivered by `add-identity-and-opa`
- [ ] 5.8 Stage 7 (Return): construct `RetrievalResponse` with `usage` envelope
- [ ] 5.9 Per-stage OTel spans with token attributes and Prometheus counter increments
- [ ] 5.10 Recreatability test: replay an audit record and assert byte-identical context

## 6. Model providers

- [ ] 6.1 `packages/shared-py/providers/` — `EmbeddingProvider`, `IntentClassifier`, `Reranker`, `Generator` protocol classes
- [ ] 6.2 Ollama adapter: embeddings, intent classification, rerank, generation; streaming where supported; usage accounting
- [ ] 6.3 Anthropic adapter: intent classification (Haiku default), generation (Sonnet optional); `usage.input_tokens`/`output_tokens` surfaced
- [ ] 6.4 OpenAI-compatible adapter: chat + embeddings; configurable `base_url`
- [ ] 6.5 Provider registry: resolve `provider:model` strings from config; health probes per provider
- [ ] 6.6 Cost table loader (`infra/costs.yaml`) and emission of `opencg_cost_usd_total`
- [ ] 6.7 Provider unit tests with recorded responses (VCR-style)

## 7. Knowledge graph (Postgres + AGE)

- [ ] 7.1 `relationship_vocab` CRUD API exposed through the pipeline service
- [ ] 7.2 Edge insert path with `state ∈ {candidate, confirmed}`, `confidence`, `evidence_uri`, `extractor_version`
- [ ] 7.3 Promote / edit / delete APIs with audit-row emission per state transition
- [ ] 7.4 `traverse_graph` implementation: openCypher over AGE with type/depth/limit; confirmed-only by default
- [ ] 7.5 Cluster job: community detection over confirmed edges (e.g., Leiden via NetworkX nightly); store cluster assignments
- [ ] 7.6 Tests: vocabulary enforcement, candidate hidden from default traversal, audit row per transition

## 8. Catalog store

- [ ] 8.1 Entity CRUD with stable UUID derivation from `(source, source_uri)`
- [ ] 8.2 Lineage chain on derived entities (chunks → parent page)
- [ ] 8.3 Freshness fields and `freshness_state` transitions driven by enrichment
- [ ] 8.4 Direct query API with filter set described in `catalog-store/spec.md`
- [ ] 8.5 Tests: idempotent re-ingest, freshness transitions, direct query

## 9. Vector index (Qdrant)

- [ ] 9.1 Bootstrap script for collections with dense + sparse vector params
- [ ] 9.2 Insert/update path keyed by `entity_id`, payload populated per spec
- [ ] 9.3 Hybrid search wrapper (dense + sparse → RRF) with filter pushdown
- [ ] 9.4 Snapshot helper to record `vector_collection` + `vector_snapshot_id` per request
- [ ] 9.5 Tests: insert→search round-trip, filter pushdown, snapshot recording

## 10. Ingestion

- [ ] 10.1 Connector framework: `discover`, `fetch`, `list_changes`, `chunk`, `metadata`; scheduler with retry/backoff; content hashing
- [ ] 10.2 Git connector (libgit2 / `pygit2`): clone or pull, walk repo, file-type matrix, tombstone on delete
- [ ] 10.3 Confluence connector: REST client, incremental sync, storage→text conversion, retain storage format in metadata
- [ ] 10.4 Custom HTTP API connector: YAML config schema, JSONPath extraction, field mapping
- [ ] 10.5 Web indexer: robots.txt + nofollow, allow-list enforcement, canonical URL, binary skip
- [ ] 10.6 Idempotency by content hash
- [ ] 10.7 Tests per connector with fixtures
- [ ] 10.8 Connector status surface for admin UI (`status`, `last_run`, `next_run`, `error_count`)

## 11. Background enrichment

- [ ] 11.1 Worker runtime (arq on Valkey)
- [ ] 11.2 Change-driven worker subscribed to `IngestEvent` stream
- [ ] 11.3 Freshness sweep cron
- [ ] 11.4 Relationship inference cron (nightly recent, weekly global)
- [ ] 11.5 Usage feedback consumer; `usage_signals` writer; `usage_score` aggregation cron
- [ ] 11.6 Tests: end-to-end change → enrichment → candidate edge visible

## 12. Entitlement + audit

- [ ] 12.1 OPA client with per-request decision cache → delivered by `add-identity-and-opa`
- [ ] 12.2 Audit row writer; immutability trigger verified
- [ ] 12.3 Audit query API (correlation/principal/time/entity/tool filters)
- [ ] 12.4 Replay endpoint: reconstruct from stored versions+snapshot; report divergence
- [ ] 12.5 Legal hold flag flow
- [ ] 12.6 Tests: immutability enforcement, replay byte-identical, replay divergence path

## 13. Observability

- [ ] 13.1 OTel collector compose service; receive OTLP from all services; export to Tempo (traces), Loki (logs), Prometheus (metrics)
- [ ] 13.2 Tempo + Loki + Prometheus + Grafana compose services with persistent volumes
- [ ] 13.3 Provision Grafana datasources and folder
- [ ] 13.4 Ship dashboards: requests/latency, per-stage latency, token spend by tenant/provider/model, ingestion health, audit volume, provider health
- [ ] 13.5 Cost emission verified end-to-end
- [ ] 13.6 Smoke test: a single MCP call produces the expected trace shape and counter increments

## 14. Admin UI

- [ ] 14.1 Scaffold Next.js (App Router) app in `services/admin-ui`
- [ ] 14.2 Query review page (list + detail with audit record and assembled context)
- [ ] 14.3 Graph management page (entity browser, candidate review queue with bulk actions, edge editor)
- [ ] 14.4 Vector neighbourhood page (top-K viewer + UMAP projection via a small Python sidecar)
- [ ] 14.5 Content management page (entity detail, tombstone, re-extract, freshness)
- [ ] 14.6 Ingestion control page (connector list, trigger runs, ingest-URL panel)
- [ ] 14.7 Token / cost dashboards (Grafana embed via signed URLs)
- [ ] 14.8 Playwright smoke test covering each page

## 15. Deployment

- [ ] 15.1 `infra/compose/docker-compose.yml` with all services
- [ ] 15.2 `dev` profile (source-mounted, hot reload)
- [ ] 15.3 `local-prod` profile (built images, persistent volumes, restricted ports)
- [ ] 15.4 `compose up` healthy within five minutes on a standard laptop (8-core / 16 GB)
- [ ] 15.5 Stub-identity guard: services refuse to boot in `local-prod` with stub-only identity
- [ ] 15.6 `make smoke` runs the end-to-end smoke test against a fresh stack

## 16. Documentation

- [ ] 16.1 `README.md` — overview, quickstart, links to spec / design / dashboards
- [ ] 16.2 `docs/ARCHITECTURE.md` — narrative version of the pipeline, mapped to the reference architecture image
- [ ] 16.3 `docs/CONNECTORS.md` — how to write a connector
- [ ] 16.4 `docs/MODEL_PROVIDERS.md` — how to add a provider
- [ ] 16.5 `docs/OPERATIONS.md` — config reference, health checks, backup/restore for catalog + audit
- [ ] 16.6 Reference architecture image saved under `docs/reference-architecture/`
