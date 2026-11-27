## ADDED Requirements

### Requirement: Qdrant collection layout

The system SHALL store vectors in Qdrant collections named `<tenant>__<source>` (single-tenant deploys still use a tenant slug for forward compatibility). Each point SHALL include a payload with `entity_id`, `source`, `classification`, `chunk_index`, `parent_entity_id`, and `content_hash`.

#### Scenario: New point inserted with payload

- **WHEN** the ingestion service inserts a vector for an entity
- **THEN** the Qdrant point payload contains all required fields
- **AND** the point ID equals the catalog `entity_id`

### Requirement: Hybrid dense+sparse search

The system SHALL support hybrid search combining dense embeddings (configured embedding model) and sparse embeddings (BM25 or SPLADE) via Qdrant's hybrid query, fused by Reciprocal Rank Fusion.

#### Scenario: Hybrid query

- **WHEN** the retrieval stage runs a hybrid search with limit 50
- **THEN** Qdrant returns up to 50 results ordered by RRF score combining dense and sparse rankings

### Requirement: Filter pushdown

Queries SHALL support payload filters (e.g., `source IN (...)`, `classification = "internal"`) that are pushed down to Qdrant, not applied in application code after the fact.

#### Scenario: Filtered search

- **WHEN** a query filters `source = "git"`
- **THEN** Qdrant evaluates the filter and returns only matching points

### Requirement: Snapshot identifier

Every retrieval call SHALL record the Qdrant collection name and a snapshot identifier (commit hash or snapshot ID) in the audit record so the exact index state can be reconstructed for replay.

#### Scenario: Snapshot recorded

- **WHEN** the retrieval stage queries Qdrant
- **THEN** the audit record contains `vector_collection` and `vector_snapshot_id`
