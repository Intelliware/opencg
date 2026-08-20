## 1. Pre-flight

- [ ] 1.1 Confirm the pre-flight decisions still hold before writing code: `source_revision` advances on a skip (D12), `updated_at` is deliberately left alone (D13), a skip refreshes chunk rows via one set-based statement behind a new index (D14), and this change does not repair `bootstrap-thin-mvp` (D15). No open questions block implementation.
- [ ] 1.2 Confirm `add-ontology-layer` is not being implemented concurrently — both changes touch code around the graph writer.
- [ ] 1.3 Fix the `chunker_version` source: replace `getattr(graphify, "__version__", "0.0.0")` at `pipeline_runner.py:300` and `chunking.py:113` with `importlib.metadata.version("graphifyy")`, failing loudly rather than defaulting. A silent default defeats the invalidation the marker exists to provide.

## 2. Chunker outcome contract

- [ ] 2.1 Define the outcome type with `symbols`, `partial`, `no_symbols`, and `extract_failed`.
- [ ] 2.2 Change `chunk_code_by_symbols` to return its chunks plus the outcome, reporting `extract_failed` at `chunking.py:171` and `no_symbols` at `chunking.py:188`.
- [ ] 2.3 Update `_extract_code` in `pipeline_runner.py` to propagate the outcome, and report `extract_failed` for its own `except` path at `:312`.
- [ ] 2.4 Update every existing caller and test that unpacks `chunk_code_by_symbols`. Includes `tests/test_code_path_materialisation.py`, which unpacks `_extract_code` as a 2-tuple in three places.
- [ ] 2.5 Track discovered-versus-captured symbols so `symbols` can require that every discovered symbol yielded a chunk. Symbols are dropped silently in two places: `_parse_line` returning `None`, and a body span that is empty after stripping. Report `partial` when any drop occurred, including when every symbol was dropped and no chunks resulted.
- [ ] 2.6 Unit tests, one per spec scenario: three non-merging functions yield exactly three chunks and `symbols`; one unparseable `source_location` among three yields `partial`; every symbol dropped yields `partial`; a statements-only file yields `no_symbols`; an empty file yields `no_symbols`; a raising extractor yields `extract_failed`; an inner-extractor failure with a successful outer extract still yields `extract_failed`.
- [ ] 2.7 Assert exact chunk counts and chunk content in the scenario tests rather than lower bounds. Review found `len(chunks) >= 3` passes when a spurious fourth chunk appears, and the fallback tests passed for any chunk lacking symbol metadata regardless of its text.

## 3. Catalog methods

- [ ] 3.1 Add the bulk ingest-state read, predicated on `tenant` plus an equality-any over `entity_id`, returning `content_hash` and raw marker metadata keyed by entity id. No `source_uri` pattern match — `entity_source_uri_uq` cannot serve a prefix `LIKE`.
- [ ] 3.2 Batch the entity-id array so a large repository does not build one oversized parameter.
- [ ] 3.3 Add the compare-and-set marker write: merges into existing metadata, scoped by tenant, leaves `body`, `title`, `source_revision`, `classification`, and `tombstoned_at` untouched, and reports rows affected.
- [ ] 3.4 Add the index on `opencg.entity (tenant, parent_entity_id)` to `infra/postgres/init/020_catalog.sql`, and document the `CREATE INDEX CONCURRENTLY IF NOT EXISTS` equivalent in `docs/OPERATIONS.md` for existing databases. Postgres creates no index for a foreign key automatically; `get_entity_with_lineage` sequentially scans on this column today.
- [ ] 3.5 Add the verified-touch: refreshes `last_verified_at` and `source_revision` on the parent, mutates no content, does not bump `updated_at`, does not clear `tombstoned_at`, and does not mark a tombstoned row fresh.
- [ ] 3.6 Extend the verified-touch to the parent's chunks as ONE set-based statement predicated on `tenant` and `parent_entity_id`, excluding tombstoned rows. Not one statement per chunk — the caller cannot enumerate chunk ids because a skipped file was never chunked.
- [ ] 3.7 Tests using the `_Pool` / `_Conn` fake pattern from `services/pipeline/tests/test_catalog.py`: bulk read shape and predicate, unknown ids absent, CAS succeeds on match, CAS affects zero rows after an overwrite, marker merge preserves other keys and columns, touch leaves a tombstone set, chunk refresh issues one statement rather than N.
- [ ] 3.8 Verify against a real database that the chunk refresh plan uses the new index and does not sequentially scan.

## 4. Marker write — stage one, gate still disabled

- [ ] 4.1 Define the marker's namespaced, versioned metadata key and its serialised shape: `content_hash`, `embedding_fingerprint` (provider, model, vector dimension), `chunker_version`, `extraction_version`, `chunk_mode`, `chunk_count`, `completed_at`.
- [ ] 4.2 Generate a per-run attempt identifier and write it to the parent row when processing begins, so the CAS predicate can identify ownership.
- [ ] 4.3 Track per-file success in `ingest_documents`: every chunk embedded and upserted, chunk count accumulated in memory, extraction not degraded, and whether the file was cut mid-flight by `--max-chunks`.
- [ ] 4.4 Capture whether `write_code_graph` succeeded for code files, and treat a caught failure as blocking completion.
- [ ] 4.5 Write the marker after the chunk loop, only when all four conditions hold. Never attach it to `doc.metadata` — chunk metadata spreads the parent's dict and would duplicate the marker into every chunk row.
- [ ] 4.6 Judge truncation per file, not per run: a file fully processed inside a bounded run earns its marker even when the run reports truncation.
- [ ] 4.7 Tests: a clean file earns a marker; `extract_failed` earns none; a `write_code_graph` failure earns none; an embed error earns none; a file cut by `--max-chunks` earns none; a file completed under `--max-documents 1` earns one.
- [ ] 4.8 Verify against a live stack that markers appear as expected — complete files marked, symbol-free files carrying `no_symbols`, nothing unexpected marked. Behaviour is unchanged at this point, so this is safe to run against real repositories.

## 5. The gate — stage two

- [ ] 5.1 Read ingest state in bulk at the top of `ingest_documents`, before the document loop.
- [ ] 5.2 Implement marker parsing that validates the schema version and never raises; malformed, truncated, and unknown-version markers are treated as absent.
- [ ] 5.3 Implement the skip decision: skip only when the marker parses, is a known version, and `content_hash`, `embedding_fingerprint`, `chunker_version`, and `extraction_version` all match.
- [ ] 5.4 On skip, call the verified-touch and continue without chunking, embedding, upserting, or extracting.
- [ ] 5.5 Tests for each poison state asserting the next run reprocesses: chunk-limit truncation, embed failure, degraded extraction, failed graph write, absent marker, malformed marker.
- [ ] 5.6 Test the inverse error explicitly: a file recorded as `no_symbols` re-ingested unchanged MUST be skipped, not reprocessed. This is the case most likely to be implemented backwards.
- [ ] 5.7 Tests for invalidating inputs: changed content, changed embedding fingerprint, changed chunker version, changed extraction version — each reprocesses.
- [ ] 5.8 Confirm the verified-touch does NOT bump `updated_at` — see D13. No code is needed for this; it is the absence of a write. Add a test pinning it, since a later "helpful" addition would silently undo the two behaviours below.
- [ ] 5.9 Test that after a re-ingest with one changed file, the changed entity sorts above unchanged ones in `list_entities`, and that unchanged entities retain their prior `updated_at`.
- [ ] 5.10 Test that `re-extract --since` now selects only chunks of changed files. This is a latent bug the gate fixes: today every ingest resets `updated_at` corpus-wide, so the flag matches nearly everything.

## 6. Marker invalidation

- [ ] 6.1 Add an operator path to invalidate markers and force a full reprocess.
- [ ] 6.2 Document it in `docs/OPERATIONS.md` next to the Qdrant collection-recreation procedure, which is the case that requires it.
- [ ] 6.3 Document the one-off full reprocess on the first run after the gate is enabled.

## 7. Skipped counts

- [ ] 7.1 Add the skipped count to `IngestionSummary`. Do NOT add a third yield to `__iter__` — `server.py:124` destructures it positionally inside a broad `except Exception`, so a third value breaks HTTP-triggered ingests while the CLI and smoke both pass. Either keep the arity at two or delete `__iter__` and convert both call sites to attribute access.
- [ ] 7.2 Add a `skipped` parameter to `RunStore.update` and pass it from `server.py`.
- [ ] 7.3 Add `skipped` to `IngestionRun` in `packages/shared-py` and mirror it in `packages/shared`.
- [ ] 7.4 Print the skipped count in the CLI summary.
- [ ] 7.5 Tests: a fully skipped run reports the right counts; an HTTP-triggered ingest still reaches `succeeded`.

## 8. Admin UI

- [ ] 8.1 Add the skipped column to `IngestionRunRow.tsx` and widen the grid header in `app/ingestion/page.tsx`.
- [ ] 8.2 Update `IngestionRunRow.stories.tsx` — the Storybook coverage requirement names this component explicitly and requires canonical, empty, and error stories.
- [ ] 8.3 Update the component's vitest coverage.
- [ ] 8.4 Check whether `ConnectorCard`'s "N files / N chunks" summary is misleading once most files are skipped, and adjust if so.

## 9. Smoke

- [ ] 9.1 Add a second ingest of the same fixture within one smoke run, after the first ingest's existing assertion block.
- [ ] 9.2 Assert the second run skips every document and produces zero chunks. Leave the existing `1 <= CHUNKS <= 19` assertion untouched — it applies to the first ingest only.
- [ ] 9.3 Place the new block BEFORE the existing tombstone step at `run.sh:296`, since a skip no longer revives a tombstoned row and would change that step's outcome.
- [ ] 9.4 Confirm the two-file fixture completes both files under the smoke's `--max-documents 10` and `--max-chunks 20` bounds, so both genuinely earn markers.

## 10. Documentation and close-out

- [ ] 10.1 Update `tools/explainer/content/01-ingestion.md`: remove "No unchanged-content short-circuit" from the gap list and describe the gate in the flow narrative.
- [ ] 10.2 Correct the explainer's description of `source_revision`. It currently claims the column answers "which version of the repo did this text come from", which the code has never done — it records the commit at which the content was last confirmed. Describe it accurately rather than aspirationally.
- [ ] 10.3 Open a follow-up change for bi-temporal revision tracking (first-seen-at plus confirmed-through), which is what would make the explainer's original claim true. See D12.
- [ ] 10.4 Open a follow-up change to reconcile `bootstrap-thin-mvp`'s ingestion spec. Four of its six `MODIFIED` blocks — *Idempotency and content hashing*, *Confluence connector*, *Custom HTTP API connector*, *Web indexer* — target requirements that exist only in the unarchived `add-foundation` and are absent from the baseline, so thin-MVP cannot be archived cleanly. `openspec validate --strict` passes on it today and will not warn anyone. See D15.
- [ ] 10.5 Run `make explainer` to regenerate `docs/explainer/index.html` and snapshot a version; confirm `make explainer-check` passes.
- [ ] 10.6 Run the full unit suites: `pytest` for pipeline and ingestion, `vitest` for admin-ui.
- [ ] 10.7 Run `bash tests/smoke/run.sh` against the live stack.
- [ ] 10.8 Run `openspec validate add-incremental-ingest --strict`.
