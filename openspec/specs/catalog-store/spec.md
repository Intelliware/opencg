# Catalog Store

## Purpose

Store and manage tenant-scoped knowledge entities, including indexed administration queries and soft deletion.
## Requirements
### Requirement: Direct query

The catalog store SHALL accept structured filter queries from the admin UI via the pipeline's `GET /entities` endpoint and MUST evaluate them using existing indexes (`entity_classification_ix`, `entity_freshness_ix`, the `entity_source_uri_uq` covering source). No body-text scan is permitted for the admin list query.

#### Scenario: Admin list filters use indexed columns

- **WHEN** the pipeline queries the catalog with filters `(source, classification, freshness_state)` and pagination `(limit, offset)`
- **THEN** the query plan touches indexed columns only (`EXPLAIN` shows index scans, no sequential scan over `entity`)

### Requirement: Tombstone (soft delete)

The catalog store SHALL support a soft-delete operation that sets `tombstoned_at = now()` on the targeted row. Tombstoning MUST be idempotent: re-tombstoning a row preserves the original `tombstoned_at`. The operation MUST NOT remove the row, MUST NOT mutate any other column, and MUST NOT cascade.

The catalog store SHALL expose a live-subset lookup that, given a tenant and a list of entity IDs, returns the IDs whose rows exist and are not tombstoned. Every caller that serves content from the vector index MUST pass its hits through this lookup and drop the rest, because tombstoning does not modify the Qdrant payload.

#### Scenario: Tombstone is idempotent

- **WHEN** a caller tombstones an already-tombstoned row
- **THEN** the row's `tombstoned_at` is unchanged
- **AND** no other column is modified

#### Scenario: Tombstoned rows are excluded from retrieval

- **WHEN** an entity is tombstoned
- **THEN** subsequent calls to `lexical_search` from the retrieval pipeline do not return it
- **AND** the dense (Qdrant) leg of hybrid retrieval does not return it, even though its Qdrant point is unchanged
- **AND** `POST /retrieve` does not include it in `fragments`

#### Scenario: Live-subset lookup

- **WHEN** the lookup is called with IDs `[A, B, C]`, where `B` is tombstoned and `C` does not exist
- **THEN** it returns `{A}`
- **AND** a call with an empty list returns an empty set without querying the database

#### Scenario: Re-ingest restores a tombstoned entity

- **WHEN** a tombstoned entity's source is re-ingested
- **THEN** its `tombstoned_at` is cleared
- **AND** it is returned by retrieval again

### Requirement: Admin list query

The catalog store SHALL expose a function callable from the pipeline that lists entities with filters `(tenant, source?, classification?, freshness_state?)`, sorted by `updated_at DESC`, paginated by `(limit, offset)`. It MUST also return a `total` count for the same filter set (single round-trip is acceptable; a second SELECT count is acceptable in v1).

#### Scenario: List with all filters

- **WHEN** the pipeline calls the list function with `tenant="default", source="git", classification="internal", freshness_state="fresh", limit=50, offset=0`
- **THEN** the function returns an ordered slice of rows plus a `total` matching the count of rows satisfying the same filters

#### Scenario: List without filters

- **WHEN** the pipeline calls the list function with only `tenant` and pagination
- **THEN** all entities for the tenant are eligible
- **AND** results are ordered by `updated_at DESC`

### Requirement: Symbol-aware chunk id derivation

For chunks produced by the symbol chunker (code files processed by `chunk_code_by_symbols`), the catalog store SHALL derive the chunk `entity_id` as `uuid5(_SYMBOL_NS, f"{parent_entity_id}:{symbol_id}")` where `symbol_id` is graphifyy's stable per-symbol identifier. For oversized symbols that get paragraph-split, the seed MUST include the sub-chunk index: `uuid5(_SYMBOL_NS, f"{parent_entity_id}:{symbol_id}:{sub_index}")`.

For chunks produced by the paragraph chunker (text, markdown, future PDF / HTML / MDX), the catalog store SHALL continue to derive the chunk `entity_id` as `uuid5(_CHUNK_NS, f"{parent_entity_id}:{chunk_index}")` as established by `bootstrap-thin-mvp`.

Both schemes MUST be deterministic: re-ingest of an unchanged input MUST produce the same chunk id.

#### Scenario: Stable symbol-chunk id across re-ingest

- **WHEN** a Python file with three functions is ingested twice without changes
- **THEN** the same three `entity_id` values appear in `opencg.entity` both times
- **AND** the upsert path is taken (no duplicate rows)

#### Scenario: Adding a function above existing ones does not renumber

- **WHEN** a developer adds a new function `helper_a` at the top of a Python file that previously had `existing_b` and `existing_c`
- **THEN** the chunks for `existing_b` and `existing_c` retain their original `entity_id` values
- **AND** a new chunk row is created for `helper_a`
- **AND** the vector index does not require re-upserting the unchanged chunks

#### Scenario: Oversized symbol sub-chunks share the parent symbol id

- **WHEN** a function whose body exceeds the symbol size limit is paragraph-split into N sub-chunks
- **THEN** each sub-chunk row carries the same parent symbol id in metadata
- **AND** each sub-chunk's entity_id is distinct via the sub_index seed

### Requirement: Evidence linkage between chunks and edges

The catalog store SHALL host a join table `opencg.relationship_evidence(edge_id, entity_id, span TEXT, extractor_version TEXT, confidence FLOAT, created_at TIMESTAMPTZ)` linking each candidate edge to the chunk(s) it was extracted from. `entity_id` MUST be a FK into `opencg.entity`. Cascading delete of a tombstoned chunk MUST NOT remove evidence rows; tombstoning is soft, and evidence is retained for audit replay.

The catalog store SHALL expose a helper `get_evidence_chunks(edge_id) -> list[EntityRef]` used by the admin UI to render evidence per edge.

#### Scenario: Evidence is written alongside a candidate edge

- **WHEN** the extractor inserts a candidate edge derived from chunk `C1`
- **THEN** a `relationship_evidence` row is written linking that edge to `C1`

#### Scenario: Tombstoning a chunk preserves evidence

- **WHEN** an admin tombstones a chunk that supports a candidate edge
- **THEN** the `relationship_evidence` row is preserved
- **AND** the chunk's body is still fetchable via `GET /entities/{id}` (which already returns tombstoned rows)

