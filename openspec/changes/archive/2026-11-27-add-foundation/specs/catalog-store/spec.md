## ADDED Requirements

### Requirement: Entity registry

The catalog SHALL maintain a registry row for every retrievable item with at minimum: `entity_id` (stable UUID), `source` (connector name), `source_uri`, `content_hash`, `title`, `owner`, `classification`, `created_at`, `updated_at`, `ingested_at`, and a free-form `metadata` JSON blob.

#### Scenario: Connector ingests a document

- **WHEN** a connector ingests a new document
- **THEN** a catalog row is created with all required fields populated
- **AND** the `entity_id` is stable across re-ingestion of the same `source_uri`

### Requirement: Source lineage

For every catalog row, the system SHALL retain the lineage chain: which connector ran, which job ID, which source revision (`source_revision`), and the parent entity if the row was derived (e.g., a chunked section of a page).

#### Scenario: Chunk linked to parent

- **WHEN** a page is split into ten chunks
- **THEN** each chunk row has `parent_entity_id` pointing at the page row
- **AND** all chunks share the page's `source_revision`

### Requirement: Freshness tracking

The catalog SHALL record `last_verified_at` and `freshness_state` (`fresh` / `stale` / `unknown`) per row. Background enrichment SHALL update these fields on a configured cadence per source.

#### Scenario: Stale after threshold

- **WHEN** `last_verified_at` is older than the configured threshold for the source
- **THEN** the row's `freshness_state` becomes `stale` after the next freshness sweep

### Requirement: Direct query

The catalog SHALL be queryable with structured filters (equality, IN, ranges over indexed fields) returning entity rows. This is the "direct query" path of the hybrid retrieval stage and SHALL NOT invoke any model.

#### Scenario: Filter by classification and owner

- **WHEN** a caller queries `classification = "internal"` AND `owner = "platform"`
- **THEN** the catalog returns matching rows ordered by `updated_at desc` with no model invocation
