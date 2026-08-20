---
id: model-providers
title: Model Providers
capabilities: model-providers
status: partial
services: pipeline, ingestion
tagline: Two model clients: local embeddings, and cloud chat for extraction.
---

## What it is

The layer that talks to AI models. There are exactly two clients, deliberately
kept concrete rather than hidden behind an abstraction:

**`OllamaEmbeddings`** turns text into vectors, running locally.
**`OllamaChat`** asks a chat model for structured JSON, used only by the
knowledge-graph extractor.

## Why it exists

Every model call costs money, leaks data, or both, so they are funnelled through
two auditable places rather than scattered across the codebase. Every call also
reports its token usage, which is what makes per-stage cost accounting possible.

The split between local and cloud is not a design preference — it is a
constraint that was discovered by probing. The Ollama Cloud key available to
this project returns `200` on `/api/tags` and `/api/chat` but **`401` on
`/api/embed`** for every model tried. So embeddings must run locally, and the
cloud key is chat-only.

## Flow

### 1. Embeddings: pick the working API path
`OllamaEmbeddings` first tries `POST /api/embed` with `{"model", "input"}`. On a
404 it falls back to the older `POST /api/embeddings` with `{"model", "prompt"}`,
then remembers which one worked for the rest of the client's life so it does not
re-probe on every call.
file: services/pipeline/src/opencg_pipeline/providers.py

### 2. Embeddings: return the vector and a token estimate
The default model `nomic-embed-text` returns **768** floats. Tokens are
estimated rather than measured, at roughly one token per four characters, since
the embeddings endpoint does not report usage.
file: services/pipeline/src/opencg_pipeline/providers.py

### 3. Chat: request JSON, not prose
`OllamaChat` calls `POST /api/chat` with `format: "json"` and a Bearer token, so
it works against Ollama Cloud. It is given a system prompt and a response
schema and returns content plus real token counts.
file: services/pipeline/src/opencg_pipeline/providers.py

### 4. Report tokens on every call
Each call increments `opencg_tokens_total{stage,model,provider,tenant,direction}`
and sets matching OpenTelemetry span attributes. This is treated as
non-negotiable in the project rules: a model call that does not report tokens is
a bug.
file: packages/shared-py/src/opencg_shared/metrics.py

### 5. Degrade instead of failing
An embedding failure logs and skips that one chunk rather than aborting the run.
An extraction failure is caught, counted, and stepped over. Model calls are
treated as unreliable by default.
file: services/ingestion/src/opencg_ingestion/pipeline_runner.py

## Facts
- Embeddings: **`nomic-embed-text`**, local Ollama at `http://ollama:11434`, **768** dimensions
- Chat: **`gemma3:4b`** on Ollama Cloud at `https://ollama.com`
- Token estimate for embeddings: `max(1, len(text) // 4)`
- Extraction confidence floor: **0.6**; extraction timeout: **30s**
- The Ollama Cloud key is **chat-only** — `/api/embed` returns 401 for this account

## Gaps
- **No provider abstraction.** Two concrete clients, no `EmbeddingProvider` / `Reranker` / `Generator` protocols. The `add-foundation` spec describes them; they are deliberately deferred until a third caller exists so the abstraction is not invented from one example.
- **No embedding cache.** Identical text embedded twice costs twice, even in the same run.
- **No retry or backoff.** A transient provider blip drops a chunk silently rather than retrying it.
- **No Anthropic or OpenAI adapter**, despite being named in the full vision.
