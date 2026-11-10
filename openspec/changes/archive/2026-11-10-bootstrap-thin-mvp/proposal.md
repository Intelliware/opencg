## Why

The `add-foundation` change describes the v0 product — twelve capabilities, full 7-stage pipeline, four ingestion connectors, OPA enforcement, replay, full admin UI. That is the right destination but it is not what we can ship first. To prove the architecture works end-to-end we need a thinner slice that ingests something, retrieves it through the pipeline, returns context to an MCP client, and lands an audit row.

A live probe of Ollama Cloud during the first attempt at the smoke test surfaced an architectural constraint that was not in `add-foundation`: this account's Ollama Cloud key returns `200` on `/api/tags` and `/api/chat`, but **`401 unauthorized` on `/api/embed`** for every model tried (`nomic-embed-text`, `qwen3-embedding`, `gemma3:4b`, `embeddinggemma`, `bge-m3`). Cloud is a viable target for chat/intent/generation in follow-up changes, but it cannot serve the embeddings call the thin MVP makes. Embeddings have to come from a local Ollama daemon — and to keep the project self-hostable, that daemon belongs in the docker-compose stack.

This change formalizes both decisions through OpenSpec rather than as inline implementation choices.

## What Changes

- **Formalize the thin-MVP scope cut** against `add-foundation`: MCP exposes one functional tool (`opencg/retrieve_for_context`); the pipeline runs four stages (identity → hybrid retrieval → assemble → return); ingestion is git-only; admin UI is one page plus a Storybook scaffold; deployment is dev-profile-only. The other v0 capabilities (`knowledge-graph`, full `model-providers` abstraction, intent classification, rerank+compress as separate stages, OPA enforcement, replay, additional connectors, full admin UI, Grafana dashboards, `local-prod` profile) are explicitly deferred to follow-up changes.
- **Adopt a local Ollama service in docker-compose** as the embeddings backend for the thin MVP. The model is pulled on first start of the service. The service is reachable from `pipeline` and `ingestion` at `http://ollama:11434`. Ollama Cloud configuration stays in place (env-driven `base_url` + `api_key`) but is reserved for chat/generation in follow-up changes; the thin MVP does not call Cloud.
- Document in `model-providers` that v0 embeddings require an Ollama-compatible host that exposes `/api/embeddings` (or `/api/embed`); Ollama Cloud's `/api/embed` is gated and MUST NOT be relied on as the embeddings backend until a future change introduces a separate provider for it.
- Reconcile the already-shipped code (env-var `OPENCG__OLLAMA__API_KEY`, Bearer-auth header in the `OllamaEmbeddings` client, default `base_url` flip to `https://ollama.com`) with these specs by capturing the requirements they implement.

## Capabilities

### New Capabilities

None — every capability touched already exists as ADDED requirements in `add-foundation`.

### Modified Capabilities

- `mcp-server`: thin-MVP scope. Only `opencg/retrieve_for_context` is implemented; the other four tools are advertised but return a `not_implemented_in_mvp` error.
- `retrieval-pipeline`: thin-MVP scope. Four stages (identity → hybrid retrieval → assemble → return); intent classification, rerank+compress, OPA-backed entitlement, intent-driven routing, deterministic-replay endpoint, and per-stage skip rules are deferred to follow-up changes.
- `model-providers`: scoped to a single embeddings-only requirement set. Adapter abstraction (`EmbeddingProvider` / `IntentClassifier` / `Reranker` / `Generator` protocols) is deferred. Embeddings backend MUST be Ollama-compatible. `api_key` and `base_url` MUST be env-overridable.
- `ingestion`: thin-MVP scope. Git connector only; Confluence, custom-api, and web-indexer are deferred.
- `admin-ui`: thin-MVP scope. Query review list + audit detail view + Storybook scaffold only. Graph editor, vector neighbourhoods, content management, ingestion control, and dashboard embeds are deferred.
- `deployment`: thin-MVP scope. `dev` profile only; `local-prod` profile, OTel collector/Tempo/Loki/Prometheus/Grafana, and persistent prod volumes are deferred. ADDS a new requirement: an Ollama service in the compose stack as the embeddings backend.
- `entitlement-audit`: thin-MVP scope. Immutable audit write + a read-only HTTP API for `list_recent` and `get_by_id`. OPA enforcement, audit query filters by entity, replay endpoint, and legal-hold workflow are deferred.

## Impact

- New file: `infra/ollama/` (entrypoint that pulls the configured embedding model on first start) and a new `ollama` service in `infra/compose/docker-compose.yml`.
- `.env.example` and `opencg.yaml` updated to default the embedding base URL to `http://ollama:11434`. Ollama Cloud env keys remain documented but commented for chat-only follow-up use.
- `openspec/specs/` baseline is unchanged because `add-foundation` is still in flight. When this change is archived, the spec deltas here become the authoritative thin-MVP contract; follow-up changes will MODIFY the same requirement names as they implement the full v0 scope.
- The `add-foundation` change remains the canonical record of the full v0 vision. A note will be appended to `add-foundation/tasks.md` clarifying that the thin-MVP subset has been split out into this change.
- The thin-MVP code already shipped (Phases A–H) is the implementation of the spec deltas in this change; `tasks.md` here ticks those boxes and lists the small remaining work (Ollama compose service + env defaults + smoke run).
