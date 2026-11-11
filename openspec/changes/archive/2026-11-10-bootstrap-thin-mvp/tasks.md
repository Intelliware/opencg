## 1. Repo scaffolding (already shipped)

- [x] 1.1 Monorepo layout (`services/`, `packages/`, `infra/`, `docs/`, `tests/`)
- [x] 1.2 Root `package.json` + `pnpm-workspace.yaml`
- [x] 1.3 Root `pyproject.toml` with uv workspace
- [x] 1.4 `Makefile` targets (`bootstrap`, `up`, `up-d`, `down`, `test`, `lint`, `format`, `ingest-git`, `smoke`)
- [x] 1.5 `.editorconfig`, `.gitignore`, `.dockerignore`, `.env.example`
- [x] 1.6 `opencg.yaml` default configuration

## 2. Storage layer (already shipped)

- [x] 2.1 Custom Postgres+AGE Dockerfile (`infra/postgres/Dockerfile`)
- [x] 2.2 Init SQL: catalog + audit (immutable, partitioned), AGE bootstrap, grants
- [x] 2.3 Qdrant compose service with named volume
- [x] 2.4 Valkey compose service with named volume

## 3. Shared packages (already shipped)

- [x] 3.1 `packages/shared` (TS) wire types
- [x] 3.2 `packages/shared-py` (Python) Pydantic mirrors
- [x] 3.3 Config loader (YAML + env-var overrides) with `OllamaCfg.api_key` field
- [x] 3.4 OTel bootstrap + Prometheus metrics helpers
- [x] 3.5 `test_config.py` covering env-override precedence

## 4. MCP server — TypeScript (already shipped)

- [x] 4.1 Service scaffold with `@modelcontextprotocol/sdk` stdio transport
- [x] 4.2 `tools/list` exposing five tool definitions namespaced `opencg/*`
- [x] 4.3 Identity stub + caller-supplied correlation-id preservation
- [x] 4.4 Pipeline client (undici) wired to `OPENCG__PIPELINE__URL`
- [x] 4.5 `/healthz` + `/readyz` HTTP endpoints for compose gating
- [x] 4.6 `not_implemented_in_mvp` error path for deferred tools
- [x] 4.7 vitest covering identity propagation, correlation-id behaviour, deferred-tool errors

## 5. Retrieval pipeline — Python (already shipped, thin-MVP scope)

- [x] 5.1 FastAPI app + lifespan + `/retrieve`, `/healthz`, `/readyz`, `/metrics`
- [x] 5.2 Stage 1 identity validation
- [x] 5.3 Stage 3 hybrid retrieval — dense (Qdrant) + lexical (Postgres FTS/trgm) fused with RRF
- [x] 5.4 Stage 6 assemble — budget enforcement + permissive classification check
- [x] 5.5 Stage 7 return — `RetrievalResponse` with `usage` envelope and `final_context_hash`
- [x] 5.6 Per-stage OTel spans with token attributes
- [x] 5.7 Prometheus counter increments via `record_stage_tokens`
- [x] 5.8 Audit row written on every request (immutable storage already shipped)
- [x] 5.9 Read endpoints `GET /audit/recent` and `GET /audit/{id}`
- [x] 5.10 Unit tests covering RRF fusion, assemble budget + classification, context hashing

## 6. Embeddings client (already shipped + this change)

- [x] 6.1 `OllamaEmbeddings` HTTP client (`/api/embeddings` legacy shape)
- [x] 6.2 `api_key` parameter + `Authorization: Bearer` header when set
- [x] 6.3 respx unit tests: bearer header present/absent, http error propagation
- [ ] 6.4 Extend client to accept `/api/embed` request body shape (`input` key) and `embeddings: [[…]]` response shape as a fallback, so Ollama Cloud and newer local Ollama versions both work
- [ ] 6.5 New respx test covering the `/api/embed` happy path

## 7. Knowledge graph (deferred — AGE only)

- [x] 7.1 AGE extension loaded + `opencg` graph created at DB init
- [ ] 7.2 Vocabulary, candidate-edge state machine, traversal — DEFERRED to follow-up change

## 8. Catalog store (already shipped)

- [x] 8.1 `opencg.entity` schema, stable UUID derivation
- [x] 8.2 Parent/child lineage for chunks
- [x] 8.3 Default freshness state set by ingestion
- [x] 8.4 Lexical search powering the BM25-ish leg of hybrid retrieval

## 9. Vector index (already shipped, dense-only)

- [x] 9.1 Qdrant collection-per-source bootstrap on first upsert
- [x] 9.2 Per-chunk upsert with thin-MVP payload shape
- [x] 9.3 Dense search wrapper used by pipeline
- [ ] 9.4 Sparse vector configuration on Qdrant — DEFERRED

## 10. Ingestion (already shipped, git only)

- [x] 10.1 `opencg-ingest` Click CLI
- [x] 10.2 Git connector: clone, walk text files, skip-list dirs, content hashing, stable IDs
- [x] 10.3 Chunker (paragraph-aware with hard-slice fallback)
- [x] 10.4 Pipeline runner — write entity, chunk, embed, upsert vector
- [x] 10.5 Unit tests covering walk, stable IDs, chunker
- [ ] 10.6 Confluence / custom-api / web-indexer connectors — DEFERRED

## 11. Background enrichment (deferred)

- [ ] 11.1 Workers — DEFERRED entirely to follow-up changes

## 12. Entitlement + audit (already shipped, hardcoded policy)

- [x] 12.1 Hardcoded role→classification allow-list inside `assemble.run`
- [x] 12.2 Audit row written with full thin-MVP schema (correlation, principal, roles, query, candidates, decisions, final ids, hash, tokens, latency)
- [x] 12.3 Immutability trigger on `opencg.audit_log`
- [ ] 12.4 OPA client + bundle — DEFERRED
- [ ] 12.5 Replay endpoint — DEFERRED (storage already shaped to support it)

## 13. Observability (already shipped — emitter side)

- [x] 13.1 OTel bootstrap (`setup_otel`) wired into pipeline service
- [x] 13.2 Prometheus metrics endpoint at `/metrics`
- [x] 13.3 Per-stage token counter increments
- [ ] 13.4 OTel collector + Tempo/Loki/Prometheus/Grafana compose services — DEFERRED
- [ ] 13.5 Dashboards + cost metric — DEFERRED

## 14. Admin UI (already shipped, query review only)

- [x] 14.1 Next.js 15 App Router scaffold + global styles + nav
- [x] 14.2 `/queries` page listing recent audit rows
- [x] 14.3 `/queries/[id]` detail page rendering `AuditRecordView`
- [x] 14.4 Components: `QueryRow`, `TokenBar`, `AuditRecordView`
- [x] 14.5 Storybook config with story per component
- [x] 14.6 vitest covering `QueryRow` and `TokenBar`
- [x] 14.7 Next build green
- [ ] 14.8 Graph editor / vector neighbourhoods / content management / ingestion control — DEFERRED

## 15. Deployment — Ollama compose service (this change)

- [x] 15.1 `infra/compose/docker-compose.yml` exists with `dev` profile and the v0 services
- [x] 15.2 Healthchecks + named volumes for storage services
- [ ] 15.3 Add an `ollama` service to compose using `ollama/ollama:0.5` (or a pinned newer tag), with a named volume `ollama-data:/root/.ollama`
- [ ] 15.4 Ollama service healthcheck that returns healthy only when the configured embedding model is loadable (e.g. `ollama list | grep -q $EMBED_MODEL`)
- [ ] 15.5 `pipeline` and `ingestion` services `depends_on: ollama: { condition: service_healthy }`
- [ ] 15.6 Pre-pull entrypoint or init script that runs `ollama pull $OPENCG__OLLAMA__EMBEDDING_MODEL` on first start
- [ ] 15.7 `.env.example` and `opencg.yaml`: default `OPENCG__OLLAMA__BASE_URL` to `http://ollama:11434`; move Cloud config into commented documentation
- [ ] 15.8 Local `.env`: point at the compose Ollama; keep the Cloud key commented for follow-up use
- [ ] 15.9 Append a note to `openspec/changes/add-foundation/tasks.md` pointing at this change as the thin-MVP contract

## 16. Smoke

- [ ] 16.1 `tests/smoke/run.sh` already exists; verify it works end-to-end against the new compose stack
- [ ] 16.2 `make up-d` and capture readiness times for each service
- [ ] 16.3 Run `make ingest-git REPO=<small public repo>` and confirm catalog + Qdrant counts
- [ ] 16.4 `make smoke` — assert audit row exists and `/audit/recent` returns it

## 17. Docs

- [ ] 17.1 README: short section pointing at this change as the v0 contract and `add-foundation` as the broader vision
- [ ] 17.2 `docs/OPERATIONS.md` stub: how to swap the embedding model + matching Qdrant vector size

## Superseded (archived 2026-11-10 by `prepare-open-source-release` task 7.5)

Archived as superseded, without syncing its spec deltas: the live baseline in `openspec/specs/` was built by the follow-up changes, which modified most of these requirements. The open tasks above are either done but were never ticked, or are covered by a later change:

| Task | Disposition |
|---|---|
| 6.4, 6.5 `/api/embed` support and test | Done: `providers.py` tries `/api/embed` first and falls back to `/api/embeddings`; covered by `tests/test_providers.py` |
| 7.2 Vocabulary, candidate-edge state machine, traversal | Shipped by `add-knowledge-graph` |
| 9.4 Sparse vectors on Qdrant | Deferred to `add-foundation` |
| 10.6 Confluence, custom-API and web connectors | Deferred to `add-foundation` (follow-ups `add-confluence-connector`, `add-custom-api-connector`, `add-web-indexer`) |
| 11.1 Background enrichment workers | Deferred to `add-foundation` |
| 12.4 OPA client and bundle; 12.5 replay endpoint | Deferred to `add-foundation` |
| 13.4 Collector and Tempo/Loki/Prometheus/Grafana | Collector shipped (compose `otel-collector`); the rest deferred to `add-foundation` |
| 13.5 Dashboards and cost metric | Deferred to `add-foundation` |
| 14.8 Graph editor, vector neighbourhoods, content management, ingestion control | Shipped by `add-admin-vector-and-content` and `add-knowledge-graph` |
| 15.3 to 15.7 Ollama compose service, healthcheck, `depends_on`, model pre-pull, `.env.example` defaults | Done: `ollama/ollama:0.30.7`, `infra/ollama/{entrypoint,healthcheck}.sh`, `.env.example` |
| 15.8 Local `.env` | Per-developer file, not tracked |
| 15.9 Note in `add-foundation` | Done: `add-foundation/tasks.md` opens with it |
| 16.1 to 16.4 Smoke and readiness checks | Done, and since replaced by `stabilize-full-smoke`; re-verified on a fresh clone in `prepare-open-source-release` phase 1 |
| 17.1 README section; 17.2 `docs/OPERATIONS.md` model-swap stub | Done: the README lists this change as the v0 base, and `docs/OPERATIONS.md` documents swapping the embedding model |
