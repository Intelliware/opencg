## ADDED Requirements

### Requirement: Chunker reports its extraction outcome

`chunk_code_by_symbols` SHALL return, alongside its chunks, an explicit outcome naming why it produced what it produced. The outcome MUST be one of:

- `symbols` — extraction succeeded and **every** symbol it discovered yielded a chunk.
- `partial` — extraction succeeded, but one or more discovered symbols yielded no chunk. Includes the case where every discovered symbol was dropped and no chunks were produced at all.
- `no_symbols` — extraction succeeded and the file legitimately contains zero symbols, so the paragraph chunker was used for the whole body. This is correct behaviour, not a failure.
- `extract_failed` — `graphify.extract` raised, and the paragraph chunker was used as a degraded fallback.

`symbols` MUST NOT be reported when any discovered symbol was dropped. The chunker discards symbols silently in at least two places — a `source_location` that will not parse, and a body span that is empty after stripping — and a file that lost symbols this way is not complete. Reporting it as complete would let it earn a completion marker and freeze the loss permanently, which is the exact failure this change exists to prevent.

The function previously returned text chunks from both the `no_symbols` and `extract_failed` paths with an identical return shape, making them indistinguishable to the caller. Callers MUST NOT infer degradation from a null code graph: `_extract_code` runs its own `graphify.extract` before delegating, so the inner extractor can fail while the outer result is non-null.

Only `symbols` and `no_symbols` represent complete work. `partial` and `extract_failed` MUST NOT earn a completion marker.

#### Scenario: Successful symbol extraction reports symbols

- **WHEN** the chunker processes a Python file containing three top-level functions, each large enough to avoid the tiny-symbol merge
- **THEN** exactly three symbol chunks are returned, one spanning each function
- **AND** the outcome is `symbols`

#### Scenario: A dropped symbol reports partial, not symbols

- **WHEN** the chunker processes a file with three discovered symbols and one of them has a `source_location` that does not parse
- **THEN** two chunks are returned
- **AND** the outcome is `partial`
- **AND** the outcome is NOT `symbols`

#### Scenario: Losing every symbol reports partial

- **WHEN** every symbol discovered in a file is dropped, so no chunks are produced
- **THEN** the outcome is `partial`
- **AND** the file does not qualify as complete

#### Scenario: A legitimately symbol-free file reports no_symbols

- **WHEN** the chunker processes a Python file containing only top-level statements
- **THEN** the paragraph chunker is used for the whole body
- **AND** the outcome is `no_symbols`
- **AND** the outcome is neither `extract_failed` nor `partial`

#### Scenario: An empty file reports no_symbols

- **WHEN** the chunker processes an empty or whitespace-only code file
- **THEN** no chunks are produced
- **AND** the outcome is `no_symbols`, because there was no work to do rather than work that failed

#### Scenario: A failed extractor reports extract_failed

- **WHEN** `graphify.extract` raises on a file
- **THEN** the paragraph chunker is used for the whole body
- **AND** the outcome is `extract_failed`

#### Scenario: Inner extractor failure is visible to the runner

- **WHEN** the outer `graphify.extract` call in `_extract_code` succeeds but the call inside `chunk_code_by_symbols` raises
- **THEN** the runner observes an `extract_failed` outcome
- **AND** the runner does not rely on the code graph being null to detect it

### Requirement: Completion marker records finished ingestion work

The ingestion service SHALL record a completion marker on a parent entity after that file's ingestion work finishes. The marker MUST be stored in the parent entity's existing `metadata` JSONB under a namespaced key carrying its own schema version, and MUST record:

- `content_hash` — the file version that completed
- `embedding_fingerprint` — embedding provider, model, and vector dimension
- `chunker_version` — the graphifyy distribution version resolved via `importlib.metadata`, an application-controlled chunker format version, and the chunker's tuning constants
- `extraction_version` — the graph-extraction contract version
- `chunk_mode` — the outcome reported by the chunker
- `chunk_count` — the number of chunks successfully embedded and upserted, counted in memory during the run
- `completed_at`

`chunk_count` MUST NOT be read back from Postgres or Qdrant. The two stores already disagree for files containing a symbol larger than `max_symbol_chars`, because each sub-chunk receives a distinct `entity_id` but they share one `source_uri`, so the catalog's unique index collapses them while Qdrant retains every point.

The marker MUST be written only when ALL of the following hold:

1. Every chunk of the file was embedded and upserted without error.
2. The chunker outcome was `symbols` or `no_symbols`. A `partial` or `extract_failed` outcome MUST NOT earn a marker.
3. Where a code graph was expected, `write_code_graph` succeeded. A caught graph-write failure MUST NOT earn a marker.
4. The file itself was not truncated mid-flight.

The marker write MUST be compare-and-set: it MUST succeed only if the parent row still belongs to the attempt that performed the work, and MUST be a no-op otherwise. Nothing serialises ingestion runs, so two runs of the same repository can interleave.

#### Scenario: A fully processed file earns a marker

- **WHEN** every chunk of a file embeds and upserts successfully, extraction was not degraded, and any expected code graph persisted
- **THEN** a completion marker is written to the parent entity's metadata
- **AND** the marker's `content_hash` equals the hash of the file that was processed

#### Scenario: A degraded extraction earns no marker

- **WHEN** the chunker reports `extract_failed` for a code file and all its fallback chunks embed successfully
- **THEN** no completion marker is written
- **AND** the next run reprocesses the file

#### Scenario: A failed code-graph write earns no marker

- **WHEN** a code file's chunks all embed successfully but `write_code_graph` raises and is caught
- **THEN** no completion marker is written

#### Scenario: A failed embedding earns no marker

- **WHEN** one chunk's embedding call raises `httpx.HTTPError` and the loop continues
- **THEN** no completion marker is written for that file

#### Scenario: A concurrent overwrite loses the marker write

- **WHEN** run A finishes a file, but run B has since rewritten that parent row under a different attempt
- **THEN** run A's marker write affects no rows
- **AND** no marker is present that misrepresents the row's contents

### Requirement: Unchanged completed files are skipped

The ingestion service SHALL skip a document when its parent row carries a completion marker that parses, declares a known schema version, and whose `content_hash`, `embedding_fingerprint`, `chunker_version`, and `extraction_version` all match the current run. A skipped document MUST NOT be chunked, embedded, vector-upserted, or graph-extracted.

Any other condition — no marker, malformed marker, unknown marker schema version, or any component mismatch — MUST cause the document to be processed normally. Parsing a marker MUST NOT raise; an unparseable marker is treated as absent.

A skipped document SHALL have its verification state refreshed without rewriting its content — on the parent row and on its chunk rows. Chunk freshness is currently maintained only as a side effect of rewriting every chunk on every run, so a skip that touched only the parent would leave the chunks frozen and the planned freshness sweep would queue them for re-checking minutes after ingestion confirmed them. The refresh MUST NOT advance `updated_at`, which is reserved to mean "when this content last changed".

The service MUST expose a way to invalidate markers so that a full reprocess can be forced. Recreating Qdrant collections is a documented operator procedure, after which every marker still matches while the vectors no longer exist.

#### Scenario: An unchanged completed file is skipped

- **WHEN** a repository is re-ingested and a file's marker matches on every component
- **THEN** no embedding call is made for that file
- **AND** no chunk row is written for that file
- **AND** the parent row and its chunk rows both have their verification state refreshed
- **AND** neither has `updated_at` advanced

#### Scenario: An edited file is reprocessed

- **WHEN** a file's content changes by one character
- **THEN** its marker's `content_hash` no longer matches
- **AND** the file is chunked, embedded, and upserted in full

#### Scenario: A changed embedding model reprocesses everything

- **WHEN** the configured embedding model changes and no file's content has changed
- **THEN** every file's `embedding_fingerprint` mismatches
- **AND** every file is reprocessed

#### Scenario: A changed extractor reprocesses everything

- **WHEN** the graph-extraction contract version changes
- **THEN** every file's `extraction_version` mismatches
- **AND** every file is reprocessed, so newly extracted concepts are picked up without a separate backfill

#### Scenario: A symbol-free file is skipped on the second run

- **WHEN** a file whose marker records `chunk_mode = no_symbols` is re-ingested unchanged
- **THEN** the file is skipped
- **AND** it is not reprocessed on every subsequent run

#### Scenario: Absent markers fail open

- **WHEN** ingestion runs against a corpus whose rows predate this change and carry no marker
- **THEN** every document is processed
- **AND** no document is skipped on the basis of a missing marker

#### Scenario: A malformed marker fails open

- **WHEN** a parent row's marker is malformed, truncated, or declares an unknown schema version
- **THEN** ingestion does not raise
- **AND** the document is processed as though no marker existed

#### Scenario: Invalidation forces a full reprocess

- **WHEN** an operator invalidates markers after recreating the Qdrant collections
- **THEN** the next run reprocesses every document
- **AND** vectors are rebuilt

### Requirement: Runs report skipped documents

`IngestionSummary` SHALL carry a count of documents skipped by the completion gate, and that count SHALL flow through the run store to `GET /runs/recent` and the CLI summary. Without it an over-aggressive gate is invisible to operators.

`IngestionSummary.__iter__` currently yields exactly two values and `server.py` destructures it positionally. Adding the count MUST NOT change that arity; either the iterator keeps yielding two values, or it is removed and every call site converted to attribute access.

#### Scenario: A fully skipped run reports its skip count

- **WHEN** a repository of 800 unchanged, completed files is re-ingested
- **THEN** the summary reports 800 skipped and 0 chunks
- **AND** the CLI prints the skipped count

#### Scenario: HTTP-triggered ingestion still succeeds

- **WHEN** an ingest is triggered through `POST /run/git` after the skipped count is added
- **THEN** the run reaches `status = succeeded`
- **AND** the run does not fail on a destructuring error

## MODIFIED Requirements

### Requirement: Ingestion HTTP surface

The ingestion service SHALL expose the following HTTP endpoints on port `8100`:

- `GET /healthz` - liveness, returns `{"status":"ok"}`.
- `GET /readyz` - readiness; returns `200` once the underlying storage (Postgres + Qdrant + Ollama embeddings) is reachable.
- `GET /connectors` - returns a JSON array of `{name, supported, reason?}` entries. `git` MUST have `supported = true`. `confluence`, `custom-api`, and `web` MUST have `supported = false` with a `reason` naming the change that will implement them.
- `POST /run/git` - body `{"repo_url": <string>}`. MUST return `{run_id, status}` immediately and execute the git ingest in a background task using the same `pipeline_runner.run` code path as the CLI.
- `GET /runs/recent` - returns the most recent 100 runs as `[{run_id, connector, repo, started_at, finished_at, status, parents, chunks, skipped, error}]`, in-memory.

Run history MAY be in-memory only. Durability across container restarts is deferred to a follow-up change.

#### Scenario: Health endpoints

- **WHEN** the ingestion service is up
- **THEN** `GET /healthz` returns `200` with `{"status":"ok"}`
- **AND** `GET /readyz` returns `200` only when the storage backends are reachable

#### Scenario: Connectors enumeration

- **WHEN** a client calls `GET /connectors`
- **THEN** the response contains `git` with `supported = true`
- **AND** the response contains `confluence`, `custom-api`, and `web` with `supported = false` and a `reason` field

#### Scenario: Run lifecycle observable via /runs/recent

- **WHEN** a `POST /run/git` triggers a background run that eventually succeeds
- **THEN** `GET /runs/recent` shows the run progressing through `queued → running → succeeded`
- **AND** the final entry carries the populated `parents`, `chunks`, and `skipped` counts

#### Scenario: Run failure surfaces error

- **WHEN** a `POST /run/git` triggers a background run that fails (e.g. unreachable repo)
- **THEN** the `/runs/recent` entry for that run reaches `status = failed`
- **AND** the entry carries a non-empty `error` string

### Requirement: Re-extract CLI subcommand

The `opencg-ingest` CLI SHALL gain a `re-extract` subcommand that walks every chunk in the catalog (filtered optionally by `--source` and `--since`) and runs `extract_for_chunk` against each. The subcommand SHALL be idempotent (skip chunks whose latest evidence row was written by the current or newer extractor version) and SHALL respect the same `extraction.timeout_seconds` and best-effort error handling as the connector hook.

`--since` filters on the chunk's `updated_at`. Because ingestion no longer rewrites unchanged rows, that column now advances only when content actually changes, so `--since` selects chunks whose content changed after the given time. Previously every ingest bumped `updated_at` across the corpus, so the filter matched effectively everything ingested after the date regardless of whether it had changed.

#### Scenario: Re-extract uses latest version filtering

- **WHEN** the operator runs `opencg-ingest re-extract --source git` and the configured `extractor_version` is `v2`
- **THEN** chunks whose latest `relationship_evidence` row already has `extractor_version = "v2"` are skipped
- **AND** chunks with no evidence row OR an older version are re-extracted

#### Scenario: Re-extract is best-effort

- **WHEN** the chat model fails on a single chunk during re-extract
- **THEN** the CLI continues with the next chunk
- **AND** logs a summary at the end with succeeded / failed / skipped counts

#### Scenario: `--since` selects only changed content

- **WHEN** a repository is re-ingested with one changed file, and the operator then runs `re-extract --since <a time before the re-ingest>`
- **THEN** only chunks belonging to the changed file are selected
- **AND** chunks of skipped files are not selected

### Requirement: Bounded Git ingestion

The Git ingestion CLI SHALL accept optional positive integer limits for maximum documents and maximum chunks. With neither limit supplied, ingestion MUST retain its existing unlimited behavior.

Document selection MUST follow deterministic connector discovery order. The document limit counts documents **examined**, including those skipped by the completion gate, so a bounded run over a largely-skipped repository may perform little work. Once the document limit is reached, no additional parent entity may be inserted. Once the chunk limit is reached, no additional chunk entity may be inserted, embedded, vector-upserted, or graph-extracted. The CLI summary MUST report the applied limits and whether the run was truncated.

Truncation MUST be judged **per file**, not per run, when deciding whether a completion marker is earned. The document limit breaks before a document is touched, so it can never leave a file partially processed; only the chunk limit can cut a file mid-flight. A file fully processed during a bounded run MUST earn its marker even when the run as a whole reports truncation.

Because a failed embedding does not increment the successful-chunk counter, a bounded run MAY insert more catalog chunk rows than the nominal chunk limit. The limit constrains successfully vectorised chunks.

#### Scenario: Default ingestion remains unlimited

- **WHEN** the operator runs the Git ingestion CLI without document or chunk limits
- **THEN** every discovered document lacking a matching completion marker is processed according to the existing connector contract
- **AND** the summary does not report truncation

#### Scenario: Document limit stops new files

- **WHEN** the operator ingests a repository with `--max-documents 1`
- **THEN** exactly one parent document is processed
- **AND** no parent or chunk from a second document is inserted
- **AND** the summary reports document truncation

#### Scenario: Chunk limit stops all downstream work

- **WHEN** the operator ingests a repository with `--max-chunks 2`
- **THEN** at most two chunk entities are successfully vectorised
- **AND** at most two embedding, vector-upsert, and text-extraction operations occur
- **AND** the summary reports chunk truncation

#### Scenario: Invalid limits are rejected

- **WHEN** the operator supplies zero or a negative document or chunk limit
- **THEN** the CLI exits before cloning with a validation error naming the invalid option

#### Scenario: A file completed inside a bounded run earns its marker

- **WHEN** the operator ingests a repository with `--max-documents 1` and that one document processes fully
- **THEN** the document earns a completion marker
- **AND** the run-level truncation flag does not prevent it

#### Scenario: A file cut mid-flight by the chunk limit earns no marker

- **WHEN** `--max-chunks` is reached partway through a file's chunk loop
- **THEN** that file earns no completion marker
- **AND** the next unbounded run reprocesses it
