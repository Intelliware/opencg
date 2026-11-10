## MODIFIED Requirements

### Requirement: Qdrant collection layout

The system SHALL store vectors in Qdrant collections named `<prefix><source>` (e.g. `default__git`). Each point MUST include a payload with `tenant`, `entity_id`, `parent_entity_id`, `source`, `source_uri`, `title`, `text`, `classification`, and `chunk_index`.

In v0 the `content_hash` payload field MAY be omitted and is deferred to the follow-up change that adds the sparse-vector configuration.

#### Scenario: Insertion populates the payload

- **WHEN** ingestion inserts a vector for a chunk
- **THEN** the Qdrant point payload contains the fields above
- **AND** the point ID equals the chunk `entity_id`

### Requirement: Hybrid dense+sparse search

In v0 Qdrant SHALL run dense-only search. The lexical leg of hybrid retrieval MUST live in Postgres (`pg_trgm` + `tsvector`) and be fused with the dense leg in application code via Reciprocal Rank Fusion. The Qdrant-side sparse-vector configuration MUST be added by a follow-up change.

#### Scenario: Dense search returns scored points

- **WHEN** the retrieval stage runs a search with a query vector and limit 50
- **THEN** Qdrant returns up to 50 points ordered by score

### Requirement: Filter pushdown

Queries SHALL support payload filters (e.g. `source IN (...)`) that are pushed down to Qdrant rather than applied in application code after the fact.

#### Scenario: Filtered search

- **WHEN** a query filters `source = "git"`
- **THEN** Qdrant evaluates the filter and returns only matching points

### Requirement: Snapshot identifier

Every retrieval call SHALL record the Qdrant collection name and a snapshot identifier in the audit record so the index state can be reconstructed.

In v0 the audit row MUST carry `vector_collection` and `vector_snapshot_id` columns. Both MAY be `NULL` until the snapshot helper is wired up.

#### Scenario: Snapshot fields exist on every audit row in v0

- **WHEN** a retrieval request completes
- **THEN** the audit row exists with `vector_collection` and `vector_snapshot_id` columns present (possibly `NULL`)
