---
id: catalog-store
title: Catalog Store
capabilities: catalog-store
status: shipped
services: postgres
stores: postgres
tagline: One Postgres table holding the authoritative copy of everything.
---

## What it is

The single Postgres table `opencg.entity` that holds the real copy of every
document and every chunk. Full text, metadata, provenance, lineage.

The mental model that matters: **Postgres is the truth, Qdrant is an index.**
If they ever disagree, Postgres wins and the index gets rebuilt.

## Why it exists

Three reasons. You need somewhere to rebuild the vector index from. You need to
answer "show me exactly what was stored" months later, which a vector cannot do.
And you need keyword search, which Postgres does natively and well.

## Flow

### 1. Write a parent row per file
Every ingested file gets one row: title, full body, content hash, git revision,
source URI, classification, and a JSONB metadata blob.
file: services/pipeline/src/opencg_pipeline/storage/catalog.py

### 2. Write a child row per chunk
Each chunk gets its own row with `parent_entity_id` pointing at the file. That
parent-child link is the lineage the admin UI walks when it shows you where a
search result came from.
file: services/pipeline/src/opencg_pipeline/storage/catalog.py

### 3. Upsert rather than insert
Writes are `ON CONFLICT (tenant, source, source_uri) DO UPDATE`, refreshing
body, title, hash, metadata, and revision, clearing any tombstone, and resetting
`freshness_state` to `fresh`. Re-ingestion updates in place instead of
duplicating.
file: services/pipeline/src/opencg_pipeline/storage/catalog.py

### 4. Index for keyword search
Two GIN indexes make this table a search engine in its own right: a full-text
index over `title || body`, and a trigram index for fuzzy and partial matching.
Together they power the lexical half of retrieval.
file: infra/postgres/init/020_catalog.sql

### 5. Serve the lexical leg
`lexical_search()` runs full-text plus trigram matching, scoped to
`tenant = $1` and excluding tombstoned rows, and returns ranked hits with their
full text ready to assemble.
file: services/pipeline/src/opencg_pipeline/storage/catalog.py

### 6. Delete softly
Removing an entity sets `tombstoned_at` rather than deleting the row, so audit
records that reference it stay meaningful forever.
file: services/pipeline/src/opencg_pipeline/admin_routes.py

## Facts
- Table: **`opencg.entity`** — one row per file, one per chunk
- Unique key: `(tenant, source, source_uri)`
- Indexes: FTS on `title || body`, trigram GIN on `body` and `title`
- Soft delete via `tombstoned_at`; hard deletes never happen
- Related tables: `relationship_evidence` links graph edges back to the chunk that justified them

## Gaps
- **Entity listing includes tombstoned rows.** The admin list has no `tombstoned_at IS NULL` filter, so soft-deleted content still appears in the browse view.
- **`freshness_state` is decorative.** It is always written as `fresh` and nothing ever recomputes or ages it.
- **No revision history.** An upsert overwrites the previous body, so you cannot see what a document used to say — only what it says now.
- **No partitioning.** Unlike the audit log, the entity table is a single unpartitioned heap.
