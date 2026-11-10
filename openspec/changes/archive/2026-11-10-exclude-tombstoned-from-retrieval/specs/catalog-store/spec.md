## MODIFIED Requirements

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
