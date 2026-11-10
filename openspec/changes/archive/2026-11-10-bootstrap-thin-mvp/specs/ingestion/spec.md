## MODIFIED Requirements

### Requirement: Connector framework

In v0 the ingestion surface SHALL be a single `opencg-ingest` CLI binary with one subcommand per connector. There MUST NOT be a scheduler, runtime discovery, or `list_changes(since)` API in v0. The full framework (`discover`, `fetch`, `list_changes`, `chunk`, `metadata`) MUST be reintroduced by the follow-up change that ships the second connector.

#### Scenario: CLI exposes the git subcommand

- **WHEN** the operator runs `opencg-ingest git <repo-url>` against a running stack
- **THEN** the CLI ingests the repository and exits `0` on success

### Requirement: Git connector

The git connector SHALL ingest a public git repository. It MUST clone the repo at HEAD with `--depth 1`, walk text files in a configurable extension allow-list, skip irrelevant directories (`.git`, `node_modules`, `.venv`, `dist`, `build`, `target`, `.next`, `.cache`), and emit one entity per file with stable IDs derived deterministically from `(tenant, source_uri)`.

In v0 the connector MUST NOT support incremental sync; re-ingest MUST be idempotent (the same `(tenant, source_uri)` updates rather than duplicates).

#### Scenario: Ingest a small public repo end-to-end

- **WHEN** the operator runs `opencg-ingest git https://github.com/<owner>/<repo>` and the storage layer is healthy
- **THEN** new rows appear in `opencg.entity` with `source = "git"` and `source_revision` set to the cloned commit SHA
- **AND** one vector point per chunk is upserted into the `git` Qdrant collection

#### Scenario: Re-ingest with unchanged content is idempotent

- **WHEN** a previously ingested repo is re-ingested without changes
- **THEN** entity rows are upserted in place (same `entity_id`) and not duplicated
- **AND** the catalog `content_hash` is unchanged

### Requirement: Confluence connector

The system SHALL NOT include a Confluence connector in v0. A follow-up change MUST add it. The CLI MUST surface a clear error if a Confluence ingest is attempted.

#### Scenario: Confluence is unsupported in v0

- **WHEN** the operator runs `opencg-ingest confluence ...` in the thin MVP
- **THEN** the CLI exits non-zero with a message naming `not_implemented_in_mvp`

### Requirement: Custom HTTP API connector

The system SHALL NOT include a custom HTTP API connector in v0. A follow-up change MUST add it.

#### Scenario: Custom API is unsupported in v0

- **WHEN** the operator runs `opencg-ingest custom-api ...` in the thin MVP
- **THEN** the CLI exits non-zero with a message naming `not_implemented_in_mvp`

### Requirement: Web indexer

The system SHALL NOT include a web indexer in v0. A follow-up change MUST add it.

#### Scenario: Web indexer is unsupported in v0

- **WHEN** the operator runs `opencg-ingest web ...` in the thin MVP
- **THEN** the CLI exits non-zero with a message naming `not_implemented_in_mvp`

### Requirement: Idempotency and content hashing

The git connector SHALL compute a `content_hash` per document. In v0 the connector MUST update the catalog row's `last_verified_at` without re-embedding when the hash is unchanged. The same skip optimisation MUST be applied by every future connector when it ships.

#### Scenario: Unchanged document skip embed

- **WHEN** the git connector encounters a file whose `content_hash` matches the catalog row
- **THEN** the catalog row's `last_verified_at` is updated
- **AND** no embedding call is made for that file
