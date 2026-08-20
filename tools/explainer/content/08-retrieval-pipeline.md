---
id: retrieval-pipeline
title: Retrieval Pipeline
capabilities: retrieval-pipeline
status: partial
services: pipeline
tagline: Turns a question into a token-budgeted packet of relevant context.
---

## What it is

The FastAPI service that answers the central question: given a query, which
pieces of the corpus should an AI model see, and in what order, within a fixed
token budget?

It runs two searches at once, merges them, applies policy, trims to budget, and
logs everything it did.

## Why it exists

An AI model with a 200k context window still gives worse answers when you fill
it with marginally relevant text. The scarce resource is not storage, it is
attention. This pillar exists to spend a token budget well and to be able to
prove afterwards how it was spent.

## Flow

### 1. Check identity
Confirms `principal` and `tenant` are present on the request envelope and passes
them through. There is no authentication here — identity arrives pre-declared by
the caller.
file: services/pipeline/src/opencg_pipeline/stages/identity.py

### 2. Run dense and lexical search in parallel
The **dense leg** embeds the question with the same `nomic-embed-text` model used
at ingest and asks Qdrant for the nearest chunks. The **lexical leg** runs
Postgres full-text and trigram search for literal matches. Both run under one
`asyncio.gather`, so the slower one sets the latency.
file: services/pipeline/src/opencg_pipeline/stages/hybrid_retrieval.py

### 3. Fuse the two rankings
The legs are merged with **Reciprocal Rank Fusion**: each result scores
`1 / (60 + rank)` from each list, and the scores add. Something ranking well in
both lists floats to the top. The constant 60 damps the head so no single list
dominates. There is no model and no tuning here — it works on ranks, not scores,
which is why it survives the two legs having incomparable score scales.
file: services/pipeline/src/opencg_pipeline/util.py

### 4. Merge metadata from both legs
Each candidate is annotated with which legs found it. If Qdrant's payload was
missing text, the Postgres copy fills it in — the catalog is always the fallback
for truth.
file: services/pipeline/src/opencg_pipeline/stages/hybrid_retrieval.py

### 5. Apply the classification policy
Each candidate's `classification` is checked against the caller's roles. A role
that is not recognised gets `public` only. Denials are recorded as
`classification_restricted` rather than silently dropped.
file: services/pipeline/src/opencg_pipeline/stages/assemble.py

### 6. Fill the token budget top-down
Walk candidates in fused-score order, estimating tokens at **0.25 per
character**, and stop including once the budget is reached. Everything that does
not fit is recorded as `budget_exhausted`. Default budget: **4,000 tokens**.
file: services/pipeline/src/opencg_pipeline/stages/assemble.py

### 7. Hash the result and audit it
The surviving fragments are hashed with SHA-256 over ordered
`(entity_id, score, text)` to produce `final_context_hash`, then one audit row is
written capturing every candidate and its verdict. The response returns
fragments, usage, and the hash.
file: services/pipeline/src/opencg_pipeline/app.py

## Facts
- Route: **`POST /retrieve`**; service port **8000**
- `top_k` default **20**; token budget default **4,000**
- RRF constant **k = 60**
- Token estimate: **0.25 tokens per character**
- Also serves `/healthz`, `/readyz`, `/metrics`, `/audit/*`, `/entities/*`, `/search/vector`, `/graph/*`
- Response includes a SHA-256 `final_context_hash` over the exact assembled context

## Gaps
- **`filters` on `/retrieve` is a no-op.** The field exists on the request type and is accepted, but never reaches the retrieval stage. Filtering only works on the admin vector-search route.
- **No reranker and no score threshold.** Fusion, policy, and budget are the only ranking forces; a cross-encoder rerank stage is specced but deferred.
- **No intent classification.** The full design has a stage that routes a query by intent; the shipped path skips straight from identity to hybrid retrieval.
- **Entitlement is a hardcoded dict**, not real policy. OPA-backed enforcement is deferred.
- **No route authentication.** The service assumes a trusted internal Docker network.
- **The knowledge graph is not consulted here.** Graph-aware retrieval is a planned follow-up.
