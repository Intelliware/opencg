## ADDED Requirements

### Requirement: Bulk ingest-state read

`CatalogStore` SHALL expose a method returning the ingest state of many entities in a single round trip, keyed by `entity_id`, yielding at minimum each row's `content_hash` and its raw completion-marker metadata.

The query MUST filter on `tenant` and an array of `entity_id` values so it uses the primary key. It MUST NOT filter by a `source_uri` prefix: `entity_source_uri_uq` is a default-collation btree that cannot serve a prefix `LIKE`, so such a query would sequentially scan the entity table. The git connector already derives every `entity_id` before the pipeline runs, so the id array is always available.

Entity ids MUST be batched rather than passed as one unbounded array, so a large repository does not build a single oversized parameter.

#### Scenario: Bulk read returns state for many ids

- **WHEN** the runner requests ingest state for 800 entity ids in one tenant
- **THEN** one query returns a mapping keyed by entity id
- **AND** each value carries that row's `content_hash` and completion-marker metadata

#### Scenario: Unknown ids are absent rather than null-filled

- **WHEN** the requested id array contains ids with no catalog row
- **THEN** those ids are absent from the returned mapping
- **AND** the caller treats absence as "never ingested"

#### Scenario: Bulk read uses the primary key

- **WHEN** the bulk read executes
- **THEN** its predicate is `tenant` plus an equality-any over `entity_id`
- **AND** it contains no `source_uri` pattern match

### Requirement: Compare-and-set completion marker write

`CatalogStore` SHALL expose a method that writes a completion marker into an entity's `metadata` JSONB, conditional on the row still belonging to the attempt that produced the marker. The predicate MUST include the tenant, matching every other statement in the module, and MUST NOT overwrite the row's `body`, `title`, `source_revision`, `classification`, or `tombstoned_at`.

The method MUST report whether it affected a row, so the caller can distinguish a published marker from one dropped by a concurrent overwrite.

The marker MUST be merged into the existing metadata object rather than replacing it, and MUST NOT be attached to the connector's per-document metadata dict. Chunk metadata is constructed by spreading the parent's metadata, so a marker placed there would be copied into every chunk row.

#### Scenario: Marker is written when the row still matches

- **WHEN** the runner publishes a marker for a row it processed and no other run has touched it
- **THEN** the marker is present in the row's metadata
- **AND** the method reports one row affected

#### Scenario: Marker write is dropped after a concurrent overwrite

- **WHEN** another run has rewritten the parent row since this attempt began
- **THEN** the marker write affects zero rows
- **AND** the method reports that no row was updated

#### Scenario: Marker write preserves other columns

- **WHEN** a marker is written to a row
- **THEN** the row's `body`, `title`, `source_revision`, and `tombstoned_at` are unchanged
- **AND** pre-existing metadata keys are retained

### Requirement: Verified-touch without content mutation

`CatalogStore` SHALL expose a method that refreshes an entity's verification state — `last_verified_at` and `source_revision` — without rewriting its content. It is used when the ingestion gate skips a document, which bypasses `insert_entity` entirely and would otherwise let verification state decay indefinitely.

The method SHALL refresh the parent row **and its chunk rows**, because chunk freshness is currently maintained only as a side effect of rewriting every chunk on every run. The chunk refresh MUST be a single set-based statement per parent, predicated on `tenant` and `parent_entity_id`, not one statement per chunk. The caller cannot enumerate chunk ids, because skipping means the file was never chunked.

`source_revision` advances to the run's commit, matching what `insert_entity` does today. The column therefore means "the commit at which this content was last confirmed present", not "the commit the content originated in". Recording both would require a second column and a schema migration, and is deferred.

The method MUST NOT bump `updated_at`. That column is left to mean "when this content last changed"; see the entity-browser ordering and `re-extract --since` behaviour that depend on it.

The method MUST NOT clear `tombstoned_at`. `insert_entity` clears it unconditionally today, so a re-ingest currently revives a tombstoned row; a skipped document must not inherit that behaviour by accident. A tombstoned row MUST NOT be marked `fresh`, because a tombstoned-and-fresh row is an incoherent state that the admin entity list would surface. Tombstoned chunk rows are excluded from the set-based refresh on the same grounds.

#### Scenario: Skipped document has its verification refreshed

- **WHEN** the gate skips an unchanged completed document
- **THEN** its parent row's `last_verified_at` advances
- **AND** its `source_revision` advances to the run's commit
- **AND** its `body` and `content_hash` are unchanged

#### Scenario: A skipped document's chunks are refreshed with it

- **WHEN** the gate skips a document that produced eight chunks
- **THEN** all eight chunk rows have `last_verified_at` advanced
- **AND** the refresh executes as one statement, not eight

#### Scenario: Verified-touch does not bump updated_at

- **WHEN** the gate skips an unchanged completed document
- **THEN** neither the parent nor its chunks have `updated_at` advanced

#### Scenario: Verified-touch does not revive a tombstoned row

- **WHEN** the gate skips a document whose parent row is tombstoned
- **THEN** `tombstoned_at` remains set
- **AND** the row is not marked `fresh`
- **AND** tombstoned chunk rows under it are likewise not refreshed

### Requirement: Index supporting parent-to-chunk lookups

The catalog SHALL carry an index on `opencg.entity (tenant, parent_entity_id)`. Postgres does not create one for a foreign key automatically, and none exists today.

Without it, the set-based chunk refresh sequentially scans the entity table once per skipped document, which is worse than the per-chunk writes it replaces. The index also serves `get_entity_with_lineage`, which selects a parent's children by `parent_entity_id` to render the admin entity detail page and sequentially scans to do so today.

The index MUST be present in `infra/postgres/init/` for fresh databases, and MUST be documented in `docs/OPERATIONS.md` as a `CREATE INDEX CONCURRENTLY IF NOT EXISTS` statement for existing deployments, since this project has no migration tooling and init SQL runs only against an empty data directory.

#### Scenario: Chunk refresh uses the index

- **WHEN** the set-based chunk refresh runs against a catalog of 45,000 rows
- **THEN** its plan uses the `parent_entity_id` index
- **AND** it does not sequentially scan the entity table

#### Scenario: Fresh and existing databases both acquire the index

- **WHEN** a new database is initialised
- **THEN** the index is created by the init SQL
- **AND** an equivalent `CREATE INDEX CONCURRENTLY IF NOT EXISTS` statement is documented for databases that already exist
