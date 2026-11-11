## MODIFIED Requirements

### Requirement: Entity registry

The catalog SHALL maintain a registry row for every retrievable item with at minimum: `entity_id`, `tenant`, `source`, `source_uri`, `content_hash`, `title`, `owner`, `classification`, `created_at`, `updated_at`, `ingested_at`, and a free-form `metadata` JSON blob.

**Thin-MVP scope:** the `entity` table also stores the document `body` so the assemble stage and admin UI can read text without a follow-up lookup. The `owner` column exists but is unused in v0.

#### Scenario: Connector ingests a document in v0

- **WHEN** the git connector ingests a new file
- **THEN** an `opencg.entity` row is created with the required fields and a populated `body`
- **AND** the `entity_id` is stable across re-ingestion of the same `(tenant, source, source_uri)`

### Requirement: Source lineage

For every catalog row, the system SHALL retain the lineage chain.

**Thin-MVP scope:** the row carries `source`, `source_uri`, `source_revision`, and `parent_entity_id`. Job IDs and run-level lineage are deferred.

#### Scenario: Chunk linked to parent

- **WHEN** a file is split into chunks
- **THEN** each chunk row has `parent_entity_id` pointing at the file row
- **AND** chunks share the file's `source_revision`

### Requirement: Freshness tracking

The catalog SHALL record `last_verified_at` and `freshness_state` per row.

**Thin-MVP scope:** columns are present and default-populated by the connector. Background freshness sweeps are deferred.

#### Scenario: Initial freshness is set

- **WHEN** a row is inserted by ingestion
- **THEN** `last_verified_at = now()` and `freshness_state = 'fresh'`

### Requirement: Direct query

The catalog SHALL be queryable with structured filters returning entity rows.

**Thin-MVP scope:** the only structured-query path used in v0 is the lexical leg of hybrid retrieval (`plainto_tsquery` + `pg_trgm` similarity). Arbitrary filtered direct-query is deferred.

#### Scenario: Lexical leg returns rows without model invocation

- **WHEN** the pipeline runs the lexical leg of hybrid retrieval
- **THEN** the catalog returns matching rows ordered by `ts_rank_cd` desc
- **AND** no model is called
