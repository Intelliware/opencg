## Context

`add-foundation` describes the full v0 product. While implementing it, we cut scope to a thin MVP so we could prove the architecture end-to-end. The cut was made as an inline comment at the top of `add-foundation/tasks.md` — that bypassed OpenSpec. This change re-routes the cut through the proper workflow.

While running the first attempt at the smoke test we hit a second issue: the configured Ollama Cloud account can chat but cannot embed. Probe results captured under D1 below. The thin MVP only calls the embeddings provider, so a local Ollama service is required.

## Goals / Non-Goals

**Goals:**
- Establish the thin-MVP contract as an OpenSpec change so the spec matches the code we shipped.
- Add a local Ollama service to docker-compose as the embeddings backend so the smoke run can succeed.
- Preserve the Ollama Cloud env wiring (`base_url`, `api_key`) so a follow-up change can adopt Cloud for chat/generation without re-plumbing.

**Non-Goals:**
- Implementing any deferred capability (knowledge graph, intent classifier, rerank, OPA enforcement, additional connectors, full admin UI, observability stack, `local-prod` profile).
- Building a provider-adapter abstraction. The thin MVP uses a single concrete `OllamaEmbeddings` client; the `model-providers/spec.md` baseline reflects that.
- Choosing a long-term cloud embeddings provider. If we decide later that we want hosted embeddings, that is its own change.

## Decisions

### D1. Ollama Cloud cannot serve embeddings on this account

Live probes on 2026-06-11 against `https://ollama.com` using the configured API key:

| Endpoint | Body | Result |
|---|---|---|
| `GET /api/tags` | — | `200 OK`, returns ~40 chat/completion models |
| `POST /api/chat` | `gemma3:4b` | `200 OK`, real completion returned |
| `POST /api/embeddings` (legacy) | `nomic-embed-text` | `404 not found` |
| `POST /api/embed` | `nomic-embed-text` | `401 unauthorized` |
| `POST /api/embed` | `qwen3-embedding`, `qwen3-embedding:8b`, `qwen3-embedding:4b` | `401 unauthorized` |
| `POST /api/embed` | `embeddinggemma`, `bge-m3`, `gemma3:4b` | `401 unauthorized` |

`qwen3-embedding` does not appear in this account's `/api/tags` listing. The catalog is chat/completion-only. The 401 on `/api/embed` is consistent regardless of model, while `/api/chat` works on the same key — i.e. the embed endpoint is gated for this account, not the key.

**Decision:** v0 does not use Ollama Cloud for embeddings. Cloud configuration stays in the codebase and `.env` but is reserved for a future change that introduces chat/intent/generation paths.

**Alternatives considered:**
- Add a separate hosted embeddings provider (Voyage AI, Jina, Cohere). Rejected for v0 because it doubles the provider surface for a thin MVP and the OSS-first goal in `add-foundation` is better served by a local model.
- Ask the user to enable an embeddings add-on on their Ollama Cloud plan. Out of scope for this change; if the plan changes later, swapping `base_url` + `api_key` is enough — no code change required.

### D2. Local Ollama runs as a compose service, not a host install

**Decision:** Add an `ollama` service to `infra/compose/docker-compose.yml` (image `ollama/ollama:0.5`). Mount a named volume for model storage. An init container or entrypoint script runs `ollama pull <embedding_model>` so first start is hands-off.

**Rationale:** keeps the OSS, self-hostable promise of the project; no host install required beyond Docker; the deployment story matches the spec ("one command bring-up").

**Alternatives considered:**
- Host install via Homebrew. Rejected: requires per-machine setup and we already denied that permission in the chat. Forces the README into "first install Ollama on your laptop", which contradicts `deployment/spec.md`.
- Ship a slim wrapper image that bundles the model. Rejected: bloats the image and makes model swaps require rebuilds.

### D3. The embedding model is configurable; `nomic-embed-text` is the default

**Decision:** Keep `OPENCG__OLLAMA__EMBEDDING_MODEL` env-overridable. Default to `nomic-embed-text` (768-dim, fast on CPU, the value already wired into Qdrant's collection vector size).

**Rationale:** users on bigger hardware can swap to `bge-m3` or `qwen3-embedding` by changing one env var and the Qdrant collection's vector size in `opencg.yaml`. Default stays small so the first-start model pull is bounded.

### D4. Provider-adapter abstraction is explicitly deferred

The full `model-providers` capability in `add-foundation` specifies four protocol types (`EmbeddingProvider`, `IntentClassifier`, `Reranker`, `Generator`) and three concrete adapters (Ollama, Anthropic, OpenAI-compatible). The thin MVP uses one concrete client (`OllamaEmbeddings`) for the only model call it makes.

**Decision:** the `model-providers/spec.md` delta in this change replaces the abstract protocol set with a smaller, concrete contract: "embeddings come from an Ollama-compatible HTTP endpoint, configurable via `base_url`, `model`, and optional `api_key`". When a follow-up change introduces intent classification or generation, it MODIFIES this requirement set and adds the protocol abstraction at that point.

**Rationale:** the abstraction was not exercised by the thin MVP code and shipping it without a second caller would have been speculative.

### D5. Already-shipped code is reconciled, not rewritten

The thin MVP code (Phases A–H, 41 tests green) implements the spec deltas in this change. Rather than tear it down and rebuild from a "clean" proposal, `tasks.md` ticks the already-completed boxes and lists only the new work (Ollama service, env defaults, smoke). A short note will be added to `add-foundation/tasks.md` directing readers here for the thin-MVP contract.

## Risks / Trade-offs

- **Risk:** `ollama/ollama` image first-start downloads ~270 MB for `nomic-embed-text` and may make `make smoke` flaky on slow networks. → Mitigation: healthcheck waits on `ollama list` returning the model; document the one-time delay in README.
- **Risk:** Compose service users (laptops) may not have GPU passthrough configured. → Mitigation: `nomic-embed-text` runs fine on CPU; document GPU as optional in `docs/OPERATIONS.md` follow-up.
- **Risk:** Qdrant collection vector size (768) is hard-coded for `nomic-embed-text` in `opencg.yaml`. Swapping to a model with a different dimension breaks search until the collection is recreated. → Mitigation: keep `vector_size` in `opencg.yaml` adjacent to `embedding_model` so the link is obvious; admin UI for collection management is a follow-up.
- **Risk:** Storing the Ollama Cloud key in `.env` while not using it is a footgun. → Mitigation: `.env.example` comment explicitly notes the key is reserved for follow-up chat use and is unused by the thin MVP.

## Migration Plan

The thin-MVP code is already in place. The remaining work to satisfy this change:

1. Add an `ollama` service (image + healthcheck + named volume + pre-pull entrypoint) to `infra/compose/docker-compose.yml`.
2. Flip the default `OPENCG__OLLAMA__BASE_URL` back to `http://ollama:11434` in `.env.example` and `opencg.yaml`. Move the Ollama Cloud example into commented documentation.
3. Update `.env` to point at the compose Ollama. Keep the Cloud key commented for future use.
4. Update `services/pipeline/src/opencg_pipeline/app.py` and the ingestion pipeline runner to handle both the legacy `/api/embeddings` and the newer `/api/embed` response shapes (we already accept both).
5. Append a note to `add-foundation/tasks.md` pointing at this change as the source of truth for the thin MVP.
6. Run `make up-d` then `tests/smoke/run.sh` and capture the result.

Rollback: stop the stack and remove the Ollama service from compose. No data migrations are required.

## Open Questions

- **OQ1:** Do we want a pinned Ollama image tag (`0.5`) or a `latest`-tracking tag? Pinned is safer for reproducibility but we'll have to bump intentionally. Default to pinned and revisit when we add CI.
- **OQ2:** Should the Ollama Cloud chat path land in the next change immediately after the smoke succeeds, or wait until the intent-classifier capability is needed? My default is "wait" — no need to wire chat until something calls it.
- **OQ3:** Do we want to ship a small admin UI panel showing "embedding model in use" + the live `/api/tags` output? Useful for debugging swaps. Defer to the follow-up that adds the model-providers abstraction.
