---
id: vector-index
title: Vector Index
capabilities: vector-index
status: shipped
services: qdrant
stores: qdrant
tagline: Qdrant. Finds text that means the same thing, not just text that matches.
---

## What it is

A Qdrant database that does exactly one job well: given 768 numbers, find the
closest stored points. That is what makes semantic search work — asking about
"login flow" can surface a chunk about "authentication handshake" even though
the two share no words.

## Why it exists

Keyword search fails whenever the asker and the author chose different
vocabulary, which in a large organisation is most of the time. Vector search
fixes that by comparing meaning instead of spelling.

Qdrant is treated as a **disposable index**, not a database of record. Every
vector can be rebuilt from Postgres, which means it can be wiped and re-created
without data loss.

## Flow

### 1. Write a point per chunk
Each chunk becomes one Qdrant point. The point id is the chunk's UUID from the
catalog, so Postgres and Qdrant always agree on identity and re-ingesting
overwrites cleanly instead of duplicating.
file: services/pipeline/src/opencg_pipeline/storage/vector.py

### 2. Store a payload alongside the vector
A small denormalised copy travels with the vector: `tenant`, `entity_id`,
`parent_entity_id`, `source`, `source_uri`, `title`, the raw `text`,
`classification`, `chunk_index`, and `symbol_id` for code. This lets a search
return readable results without a round trip to Postgres.
file: services/ingestion/src/opencg_ingestion/pipeline_runner.py

### 3. Route into a per-source collection
Collections are named `{collection_prefix}{source}`, so git content lands in
**`default__git`**. Splitting by source means one connector can be re-indexed
without touching the others.
file: services/pipeline/src/opencg_pipeline/storage/vector.py

### 4. Search at query time
`search()` embeds the query, asks every matching collection for its top `k`, then
sorts the merged list by raw score. The admin explorer uses `search_all()`
instead, which fuses across collections with reciprocal rank fusion so no single
collection dominates on score scale alone.
file: services/pipeline/src/opencg_pipeline/storage/vector.py

## Facts
- Engine: **Qdrant v1.12.4**, ports 6333 (HTTP) and 6334 (gRPC)
- Vector size: **768**; distance: **cosine**
- Collection naming: `default__<source>`, e.g. `default__git`
- Point id = catalog `entity_id`, so writes are idempotent upserts
- Two search modes: raw-score merge for `/retrieve`, RRF fusion for the admin explorer

## Gaps
- **Dense search is not tenant-filtered.** The payload carries `tenant` but `/retrieve` never passes it as a Qdrant filter. Isolation currently relies on one tenant per deployment.
- **Tombstoned chunks can still surface.** Soft-deleting an entity in Postgres excludes it from the lexical leg, but the vector stays in Qdrant until something removes it.
- **No snapshot or versioning.** `vector_snapshot_id` exists in the audit schema and the response type but is always null, so an audit row cannot pin the exact index state it searched.
- **No quantisation or payload indexes**, so this is untuned for large corpora.
