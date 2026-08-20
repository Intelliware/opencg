## MODIFIED Requirements

### Requirement: Symbol identity flows through the catalog

The catalog `metadata` JSONB on chunks produced by `chunk_code_by_symbols` MUST include:

- `symbol_id` (graphifyy's stable per-symbol id derived from the file's **repo-relative path**, e.g., `auth_middleware_verify_token`; it MUST NOT contain a transient or randomly-generated filename stem)
- `symbol_kind` (one of `class`, `function`, `method`, `module`)
- `start_line`, `end_line` (integers)
- `extractor_version` (e.g., `graphifyy/0.8.38`)

These fields MUST be queryable via the existing `GET /entities/{id}` endpoint without changes to the route schema.

The chunk's `entity_id` MUST be derived as `uuid5(_SYMBOL_NS, f"{parent_entity_id}:{symbol_id}")` for symbol-aligned chunks. Because `symbol_id` derives from the stable repo-relative path rather than a transient temp filename, re-ingest of an unchanged file produces stable IDs and upserts are idempotent when they occur.

Re-ingest of an unchanged, previously-completed file no longer performs those upserts at all: the ingestion completion gate skips the file before chunking. Stability of `entity_id` remains the guarantee that makes skipping safe, because it is what lets a marker written by one run describe the rows a later run would have produced. Files without a matching completion marker still take the upsert path unchanged.

#### Scenario: Symbol chunk metadata is queryable

- **WHEN** an admin calls `GET /entities/{chunk_id}` on a symbol-aligned chunk
- **THEN** the response's `metadata` block contains `symbol_id`, `symbol_kind`, `start_line`, `end_line`, and `extractor_version`

#### Scenario: Idempotent re-ingest of unchanged code

- **WHEN** a repo is re-ingested without changes and its files carry matching completion markers
- **THEN** existing symbol chunks have unchanged `entity_id` values
- **AND** no duplicate rows are created, because the files are skipped rather than upserted
- **AND** no symbol chunk's `symbol_id` contains a transient temp-file stem
- **AND** the existing graph concepts and edges are unchanged

#### Scenario: Re-ingest without a marker still upserts in place

- **WHEN** a repo is re-ingested without changes but its files carry no completion marker
- **THEN** the files are processed in full
- **AND** the catalog rows upsert in place with unchanged `entity_id` values (no duplicate rows)

### Requirement: Graph rows persist via a single transaction

The `graph_writer.write_code_graph` function SHALL wrap all node and edge inserts for a single file in one Postgres transaction acquired from the catalog's connection pool. A failure on any insert MUST roll back every prior insert for that file. The function MUST return `(concepts_written, edges_written)` counts so the caller can record metrics.

A rolled-back graph write MUST NOT abort the ingest — the chunk rows and vectors written before it stand — but the caller MUST record that the file's graph did not persist, and that file MUST NOT earn an ingestion completion marker. Without this, a file whose code graph silently failed would be skipped on every subsequent run and never acquire its graph, because the full re-ingest that repairs it today would no longer occur.

#### Scenario: Transaction wraps multi-statement write

- **WHEN** the writer processes one file's nodes and edges
- **THEN** all SQL statements execute inside a single `BEGIN/COMMIT` block
- **AND** the returned counts equal the number of rows successfully inserted

#### Scenario: A rolled-back graph write blocks completion

- **WHEN** `write_code_graph` raises for a code file and the ingest continues
- **THEN** that file earns no completion marker
- **AND** the next run reprocesses the file and retries its graph
