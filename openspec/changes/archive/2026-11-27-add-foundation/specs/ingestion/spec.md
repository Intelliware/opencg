## ADDED Requirements

### Requirement: Connector framework

The system SHALL provide a connector framework with a uniform interface: `discover()`, `fetch(uri)`, `list_changes(since)`, `chunk(document)`, and `metadata(document)`. New connectors SHALL be addable by implementing the interface; the framework SHALL handle scheduling, retries, rate limiting, content hashing, and dispatch into catalog + vector + graph pipelines.

#### Scenario: New connector registered

- **WHEN** a connector module is registered with the framework
- **THEN** it appears in `ingestion/connectors` discovery and can be scheduled by the admin UI
- **AND** invoking it runs `discover` and `fetch` against the source, then emits standardized `IngestEvent`s

### Requirement: Git connector

The git connector SHALL ingest a configured list of repositories. For each repo it SHALL track the current commit SHA in catalog `source_revision`, fetch changed files since the last commit, and index code/text/markdown according to a configurable file-type matrix.

#### Scenario: New commits indexed

- **WHEN** the git connector polls a configured repo and finds new commits
- **THEN** changed files are re-ingested, the `source_revision` advances, and removed files are tombstoned in the catalog

### Requirement: Confluence connector

The Confluence connector SHALL ingest spaces specified in configuration, paginate via the Confluence REST API, respect `since` timestamps for incremental sync, and convert page bodies (storage format) to plain text for embedding while retaining the storage format in `metadata`.

#### Scenario: Incremental Confluence sync

- **WHEN** the connector runs after a previous successful sync
- **THEN** it requests only pages updated since the last `synced_at` and ingests them

### Requirement: Custom HTTP API connector

The system SHALL provide a generic HTTP API connector configurable via YAML: base URL, auth (bearer/basic/header), list endpoint, item endpoint, JSONPath for record extraction, and field mapping into the standard `IngestEvent` shape.

#### Scenario: API connector config

- **WHEN** an admin defines a YAML config for a custom API
- **THEN** the connector polls on the configured cadence and ingests records mapped through the JSONPath spec

### Requirement: Web indexer

The system SHALL provide a web indexer that crawls **only allow-listed domains** configured per deploy, respects `robots.txt`, honours `nofollow`, persists the canonical URL as `source_uri`, and skips binary/non-HTML responses by default.

#### Scenario: Allow-list enforced

- **WHEN** a crawl finds a link to a domain not on the allow-list
- **THEN** the link is recorded but not fetched
- **AND** the audit record for the crawl notes the skipped URL

#### Scenario: robots.txt respected

- **WHEN** `robots.txt` disallows a path
- **THEN** the indexer does not fetch that path

### Requirement: Idempotency and content hashing

Every connector SHALL compute a `content_hash` per document and SHALL NOT re-embed or re-extract relationships when the hash is unchanged.

#### Scenario: Unchanged document

- **WHEN** a fetch returns content with the same hash already in the catalog
- **THEN** only `last_verified_at` is updated; no embeddings or relationship extraction run
