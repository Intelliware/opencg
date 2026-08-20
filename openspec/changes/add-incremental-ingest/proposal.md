## Why

Every git re-ingest re-chunks and re-embeds the entire repository. `content_hash` is computed for every file, written to the catalog, and never read back — the only reads are for admin display. Embedding is one sequential HTTP call per chunk, so a repo producing 45,000 chunks pays 45,000 round trips on every run, plus a second model call per prose chunk for graph extraction. Fixing one typo costs the same as the first ingest.

The obvious fix — compare `content_hash` and skip when it matches — is unsafe, and that is why this change is not a two-line patch. The parent row is written **before** chunking begins, so a file carries a current, correct-looking hash in four routine situations where its downstream work never completed: `--max-chunks` breaks mid-file after the parent row exists; a per-chunk embedding error logs and continues; no transaction spans parent plus chunks, so a crash commits the parent and loses the rest; and a transient graphifyy failure silently swaps a code file to text chunking and skips its code graph. Today the wasteful full re-ingest is the **only** self-repair for all four. A hash-keyed skip would freeze every one of them permanently and silently — strictly worse than the waste it removes.

## What Changes

- **A completion marker replaces the hash as the skip key.** Stored in the parent entity's existing `metadata` JSONB under a namespaced, versioned key, it records the `content_hash` that completed, an `embedding_fingerprint` (provider, model, vector dimension), a `chunker_version` (graphifyy version plus an application-controlled chunker format version and its constants), an `extraction_version`, the `chunk_mode` that was actually used, `chunk_count`, and `completed_at`.
- **A file is skipped only when the marker parses, is a known version, and every identity component matches.** Absent, malformed, unknown-version, or any mismatch means process normally. Absent fails open by design: no existing row has a marker, so the first run after this ships reprocesses the corpus once.
- **The marker is earned, not assumed.** It is written only after every chunk of that file embedded and upserted without error, extraction was not degraded, the code graph persisted where one was expected, and the file was not truncated mid-flight. Truncation is judged **per file**, not per run.
- **The chunker reports why it produced text chunks.** `chunk_code_by_symbols` currently returns plain text chunks from two different places — extraction raised, or the file genuinely has no symbols — with identical return shape. The second is spec-mandated correct behaviour. Without distinguishing them, either degraded files freeze forever or every symbol-free source file reprocesses forever. The function gains an explicit outcome so the marker can tell them apart.
- **Marker publication is compare-and-set.** Nothing serialises ingests — every `POST /run/git` spawns a background task — so two runs of the same repo can interleave. The write is conditional on the row still belonging to the attempt that did the work.
- **Skipped files are still touched.** A skip bypasses `insert_entity`, so a lightweight catalog method refreshes verification state without rewriting content.
- **Markers are invalidatable.** Recreating Qdrant collections is a documented operator procedure, after which every marker still passes and nothing re-ingests. An explicit invalidation path prevents that trap.
- **Runs report what they skipped.** `IngestionSummary`, `RunStore`, `GET /runs/recent`, and the admin ingestion page all carry a skipped count. This is a safety surface, not cosmetics: an over-aggressive gate is otherwise invisible.

Not a breaking change. Default behaviour on a corpus with no markers is identical to today.

## Capabilities

### New Capabilities

None. This change modifies existing capabilities only.

### Modified Capabilities

- `ingestion`: ADDs incremental re-ingest gated on a completion marker and the chunker outcome contract. MODIFIES *Bounded Git ingestion* (per-file truncation semantics, whether bounds count examined or processed documents, and the now-false scenario asserting every discovered document and chunk is processed) and *Ingestion HTTP surface* (the enumerated `/runs/recent` payload gains `skipped`).
- `catalog-store`: ADDs a bulk ingest-state read, a compare-and-set marker write, a verified-touch that mutates no content and refreshes a skipped file's chunk rows in one set-based statement, and an index on `(tenant, parent_entity_id)` that the refresh requires.
- `knowledge-graph`: MODIFIES *Idempotent re-ingest of unchanged code*, whose scenario asserts "the catalog rows upsert in place" — under a skip, no upsert occurs. Also states that a failed code-graph write blocks completion.
- `admin-ui`: MODIFIES the ingestion run history to surface the skipped count.

## Impact

- **No new column, but one new index.** The marker lives in the existing `metadata JSONB`, deliberately avoiding the absent migration tooling — init SQL runs only against an empty data directory. The set-based chunk refresh does require an index on `opencg.entity (tenant, parent_entity_id)`, which Postgres does not create for a foreign key automatically. An index is not part of the data contract — its absence degrades speed, not correctness — and it can be added to a live database with `CREATE INDEX CONCURRENTLY IF NOT EXISTS`. It is also already owed: `get_entity_with_lineage` sequentially scans on that column today.
- `services/ingestion/src/opencg_ingestion/chunking.py`: `chunk_code_by_symbols` gains an outcome in its return.
- `services/ingestion/src/opencg_ingestion/pipeline_runner.py`: the gate at the top of the document loop, per-file success and degradation tracking, the marker write after the chunk loop.
- `services/pipeline/src/opencg_pipeline/storage/catalog.py`: three new methods. `infra/postgres/init/020_catalog.sql` gains the index, with the `CREATE INDEX CONCURRENTLY` equivalent documented in `docs/OPERATIONS.md` for existing databases.
- `services/ingestion/src/opencg_ingestion/runs.py`, `server.py`, `cli.py`: skipped counts. Note `IngestionSummary.__iter__` yields exactly two values and `server.py` unpacks it — a third value breaks HTTP-triggered ingests only, invisible to the CLI and the smoke.
- `packages/shared` and `packages/shared-py`: `skipped` on `IngestionRun`.
- `services/admin-ui`: `IngestionRunRow.tsx` plus its mandatory `*.stories.tsx` neighbour, and the grid header in `app/ingestion/page.tsx`.
- `tests/smoke/run.sh`: a second-ingest assertion block, placed before the existing tombstone step, leaving the current assertions untouched.
- `tools/explainer/content/01-ingestion.md`: its gap list names "No unchanged-content short-circuit" by name.
- **Interaction with `add-ontology-layer`.** That change defers backfilling unclassified concepts, which is only safe while re-ingest redoes everything and picks up new classifications for free. This change removes that. The marker therefore carries an `extraction_version` so an ontology or extractor change invalidates it. The two changes should not be implemented concurrently — both touch code around the graph writer.
- **Two operator-visible behaviour shifts, both improvements, both silent.** `updated_at` is deliberately not bumped on a skip, so the `/entities` browser reorders from "most recently ingested" — arbitrary within a run, since every row shared a timestamp — to "most recently changed". And `re-extract --since`, which filters on that column, starts selecting only genuinely changed content instead of nearly everything ingested after the date. Both are captured as spec scenarios so they are tested rather than discovered as bugs.
- **Operator deletions start sticking.** `insert_entity` clears `tombstoned_at` unconditionally, so re-ingest currently revives anything an admin tombstoned. A skipped file no longer does. Better behaviour, adopted deliberately rather than inherited.
- **Operator-visible one-off**: the first run after this ships reprocesses the whole corpus, which also repairs any file left incomplete by a past interrupted run. Documented in `docs/OPERATIONS.md`.
- **`bootstrap-thin-mvp` is not repaired here.** Four of its six ingestion `MODIFIED` blocks target requirements that exist only in the unarchived `add-foundation` and are absent from the baseline, so it cannot be archived cleanly — and `openspec validate --strict` passes on it today without warning. One of those four also contradicts this change. Recorded as a follow-up rather than fixed from inside this one.
