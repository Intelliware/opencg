## Context

Git re-ingestion currently redoes all work unconditionally. `content_hash` is written to every catalog row and read only for admin display. Embedding runs one sequential HTTP call per chunk with no batching, and prose chunks incur a second model call for graph extraction, so re-ingesting an unchanged repository costs the same as the first ingest.

Three constraints shape the design:

- **The parent row is written before its chunks exist.** `opencg.entity.parent_entity_id` is a foreign key to `entity`, so the file's row must be committed before any chunk row references it. The file's hash is therefore recorded at the *start* of its work, and `content_hash` is `NOT NULL`, so it cannot simply be deferred.
- **No transaction spans a file's work.** Each `insert_entity` is its own autocommit statement, and both the embedding loop and the graph write are best-effort by design.
- **No migration tooling exists.** `infra/postgres/init/*.sql` runs only against an empty data directory, so any new column requires a hand-written `ALTER TABLE` for every existing deployment.

This design went through three rounds of adversarial review before reaching the artifacts stage. Several decisions below record positions that were rejected during that process, because the rejected version is the one a future reader is most likely to propose again.

## Goals / Non-Goals

**Goals:**

- Skip files whose ingestion demonstrably completed and whose inputs have not changed.
- Never skip a file whose work did not complete, including after crashes, bounded runs, embedding errors, and degraded extraction.
- Never permanently reprocess a file that is legitimately complete — the inverse error is equally bad and less obvious.
- Make skipping visible to operators, and reversible without database surgery.
- Require no new column. One index is added; see D14 for why that is a weaker claim rather than the same one.

**Non-Goals:**

- **Chunk-level reconciliation.** A changed file is reprocessed in full. Re-embedding forty chunks instead of one is negligible next to skipping tens of thousands.
- **Deletion detection, tombstoning, orphan cleanup, vector-payload filtering, and the knowledge-graph lifecycle.** These form a coherent follow-up that reaches into five subsystems; bundling them turns a contained change into a risky one.
- **Git commit-diff detection.** Asking git what changed between two commits would let us skip the clone and the walk entirely, but it requires abandoning the shallow clone and breaks whenever history is rewritten. It layers cleanly on top of this later.
- **Serialising concurrent ingestion runs.** Compare-and-set makes concurrency safe rather than impossible.
- **Bi-temporal revision tracking.** Recording both the commit at which content first appeared and the commit through which it was last confirmed is the better data model, and it is deferred to a named follow-up. See D12.
- Durable run history, retries, scheduling, and new connectors.

## Decisions

### D1. Gate on a completion marker, not on the content hash

**Decision.** Skipping is keyed on a marker written *after* a file's work finishes, not on the `content_hash` written before it starts.

**Rationale.** A matching hash does not imply completion. Four paths in current code produce a file with a current, correct-looking hash and incomplete downstream work: `--max-chunks` breaking mid-file after the parent row exists (`pipeline_runner.py:130`, and `test_chunk_limit_stops_downstream_work` asserts exactly this state); a per-chunk `httpx.HTTPError` that logs and continues (`:160`); a crash or SIGTERM between the parent write and the end of the chunk loop; and a graphifyy failure that swaps a code file to text chunking and skips its code graph (`:312`).

Today the wasteful full re-ingest is the only self-repair for all four. A hash-keyed gate would freeze each of them permanently and silently — strictly worse than the waste it removes, because waste is visible and silent data loss is not.

**Alternatives rejected.** *Move the hash write to the end.* Blocked by the foreign key and the `NOT NULL` constraint; the row must exist first and cannot be written blank without putting a lie in the data. *Wipe and rebuild a file's chunks on every change.* Attractively simple, and it also removes orphans — but it forces re-extraction of graph data for chunks that did not change, which is more expensive than the embedding it saves.

### D2. The marker attests to what ran, not to what is installed

**Decision.** The marker records `chunk_mode` — the outcome the chunker actually reported — alongside the versions of the components involved.

**Rationale.** An earlier draft recorded only the installed graphifyy version, which a transient extraction failure does not change. A file that fell back to text chunking would therefore match on every component and be skipped forever, keeping the wrong chunks and never acquiring its code graph. That is path four of D1 surviving the fix meant to close it.

The obvious detector — `code_graph is None` in the runner — does not work. `_extract_code` calls `graphify.extract` and then calls `chunk_code_by_symbols`, which calls `graphify.extract` again independently. The inner call can fail while the outer result is non-null, so the runner's view of the code graph says nothing about how the chunks were produced.

### D3. Distinguish degraded fallback from legitimate fallback

**Decision.** `chunk_code_by_symbols` returns an explicit outcome of `symbols`, `no_symbols`, or `extract_failed`. Only `extract_failed` withholds a marker.

**Rationale.** The function returns paragraph chunks from two places with an identical shape: extraction raised (`chunking.py:171`), and the file genuinely has no symbols (`chunking.py:188`). The second is mandated correct behaviour — `openspec/specs/ingestion/spec.md` requires it, with a scenario named "File with no symbols falls back."

Without separating them there is no safe rule. Treat code-file-with-text-chunks as incomplete and every `__init__.py`, constants module, and top-level script reprocesses on every run forever. Treat it as complete and the degraded files freeze. The information exists inside the function; it simply is not reported. This is the only change in this design that alters an existing function signature.

**Course correction after T1 review.** The first version of this decision defined `symbols` as "at least one symbol chunk was produced." Review reproduced the consequence: a file with three symbols, one of which has an unparseable `source_location`, returns two chunks and reports `symbols`. The chunker drops such symbols silently — at `chunking.py` when `_parse_line` returns `None`, and again in the emit loop when a body span is empty after stripping — so a partially-captured file would have reported itself complete, earned a marker, and frozen the loss permanently. That is the precise failure this design exists to prevent, reintroduced through the definition rather than the code.

The outcome set therefore gains a fourth value, `partial`, meaning extraction succeeded but at least one discovered symbol yielded no chunk. `symbols` now requires that **every** discovered symbol yielded a chunk. Only `symbols` and `no_symbols` earn a marker.

`partial` is a distinct value rather than being folded into `extract_failed` for two reasons. It keeps `extract_failed` meaning what its name says — the extractor raised — which review flagged as already strained. And it makes silent symbol loss countable, so an operator can see how often graphifyy is dropping symbols instead of inferring it from a marker that never appears.

### D4. Publish the marker under compare-and-set

**Decision.** The marker write is conditional on the parent row still belonging to the attempt that produced it, and reports whether it affected a row.

**Rationale.** Nothing serialises ingestion. Every `POST /run/git` spawns a background task, and the only lock in `runs.py` guards the in-memory deque. Two runs of the same repository can interleave such that one publishes a marker describing work the other's row no longer reflects.

The two independent reviewers disagreed here — one constructed a corrupting interleaving, the other traced the same territory and judged the outcome benign because chunk ids are deterministic. The dissent is recorded because it is probably correct: with deterministic ids, a marker published while another run is mid-flight still truthfully attests that a complete chunk set exists for that content, and what the losing run leaves behind is orphan rows, which is today's behaviour and the follow-up's problem. The guard is adopted anyway because it costs one predicate and removes the need to be right about that reasoning.

### D5. Store the marker in existing JSONB

**Decision.** The marker lives in `opencg.entity.metadata` under a namespaced, versioned key. No new column. (D14 later adds an index for an unrelated reason; the marker itself needs nothing.)

**Rationale.** A new column means a hand-written `ALTER TABLE` for every existing deployment, since init SQL only runs against an empty data directory. JSONB avoids that entirely.

Two properties make this safe. `insert_entity` replaces `metadata` wholesale on conflict, so reprocessing a file wipes its old marker before a new one is earned — a reprocess that dies halfway leaves no marker rather than a stale one. And `insert_entity` and `tombstone` are the only two writers to `opencg.entity`, the latter touching one column, so nothing else can clobber it.

The marker carries its own copy of `content_hash` rather than referencing the column. Whenever a marker exists the two are necessarily equal, so the copy is redundant in the happy path — its value is that the marker validates standalone. If anything ever writes that column independently, the marker stops matching and the file is reprocessed, rather than silently continuing to be trusted.

**Constraint.** The marker must never be attached to the connector's per-document metadata dict. Chunk metadata is built as `{**doc.metadata, **ch.metadata, ...}`, so a marker placed there would be duplicated into every chunk row.

### D6. Absent, malformed, and unknown-version markers all fail open

**Decision.** Anything other than a parseable marker of a known version whose components all match causes normal processing.

**Rationale.** No existing row has a marker, so the corpus reprocesses once after this ships. That is the correct direction: inverting the polarity would freeze everything. `metadata` is free-form JSONB and exposed to future writers, so parsing must be validated and must never raise.

### D7. Markers must be invalidatable

**Decision.** Ship an explicit way to invalidate markers and force a full reprocess.

**Rationale.** `docs/OPERATIONS.md` documents recreating Qdrant collections as a supported procedure. After that every marker still matches while the vectors are gone, so nothing re-ingests and the index stays empty. The marker attests to a past event and cannot detect later loss in another store. An escape hatch is cheaper and more honest than trying to make the marker self-validating.

### D8. Carry an extraction version so ontology work is not stranded

**Decision.** The marker records an `extraction_version`, and a change to it invalidates every marker.

**Rationale.** `add-ontology-layer` explicitly defers backfilling unclassified concepts. That deferral is safe only because re-ingesting currently redoes everything and picks up new classifications for free. This change removes that, silently converting an optional follow-up into a required one. Versioning extraction restores the property at negligible cost.

### D9. Skipped rows are touched, but not revived

**Decision.** A skip refreshes `last_verified_at` via a method that mutates no content, does not clear `tombstoned_at`, and does not mark a tombstoned row fresh.

**Rationale.** A skip bypasses `insert_entity`, so verification state would otherwise decay indefinitely. But `insert_entity` also clears `tombstoned_at` unconditionally, meaning re-ingest currently revives operator-deleted rows. A skipped file will no longer revive them — a change in tombstone behaviour arriving inside a change that declares tombstones out of scope. It is the better behaviour and is adopted deliberately rather than inherited by accident. A tombstoned-and-fresh row is incoherent and the admin entity list would surface it, so the touch must not produce one.

### D10. Bounds are judged per file

**Decision.** Whether a marker is earned depends on whether *that file* was cut mid-flight, not on the run's truncation flags.

**Rationale.** `--max-documents` breaks at the top of the document loop before `insert_entity`, so it can never leave a file partly processed; only `--max-chunks` can. Read as a run-level rule, "no marker during a truncated run" would refuse to mark any file in a bounded run and silently disable the feature. The smoke runs bounded, so this would have shipped broken.

The document bound counts documents *examined*, including skipped ones, so a bounded run over a largely-skipped repository does little work. That is a semantic choice, recorded here because the baseline requirement did not have to distinguish the two before skipping existed.

### D11. `chunk_count` is counted in memory, never read back

**Decision.** The marker's chunk count comes from tracking successes during the run.

**Rationale.** The two stores already disagree. A symbol exceeding `max_symbol_chars` is split into sub-chunks that each receive a distinct `entity_id` but share one `fragment_uri`, so `entity_source_uri_uq` collapses them into a single catalog row while Qdrant retains every point. Any count read back from either store would be wrong for such files. This pre-existing defect is named, not fixed, here.

### D12. A skipped file's `source_revision` advances, and bi-temporal tracking is a named follow-up

**Decision.** The verified-touch advances `source_revision` to the current HEAD, matching what `insert_entity` does today. Recording *both* the commit at which content first appeared and the commit through which it was last confirmed is deferred to a follow-up change.

**Rationale.** There are two defensible readings of the column. "The commit this content came from" — a file written in January and untouched since should still say January. Or "the commit at which we last confirmed this content is present" — it advances to today. Both are true statements about different facts, and one column cannot hold both.

Advancing is chosen because it is what happens today: `insert_entity` overwrites `source_revision` on every run regardless of whether the file changed. Skipping without advancing would silently flip that behaviour, and a change about avoiding redundant work is the wrong place to hide a semantic change to a provenance column.

**The better model, and why it waits.** Two columns — first-seen-at and confirmed-through — answer both questions from one row, and yield a third for free: content stable across a known commit range, which is a real freshness signal for retrieval. It is deferred because it requires a new column, and this project has no migration tooling, so every existing deployment would need a hand-written `ALTER TABLE`. Requiring no new column is a deliberate property of this design — D14 adds an index, which is a materially weaker imposition than a column, and the distinction is the reason one is accepted here and the other is not. The marker cannot substitute: `insert_entity` replaces `metadata` wholesale, so a first-seen value stored there would not survive a reprocess triggered by a model or chunker change, which is exactly when content has *not* changed and the value must persist.

Note that this is a validity window for the current content only, not true bi-temporality — when a file changes, the previous window is overwritten. Versioned history would need a row per content version and is a substantially larger change.

**Consequence.** `tools/explainer/content/01-ingestion.md` describes `source_revision` as answering "which version of the repo did this text come from," which the code has never done. That text is wrong today and stays wrong under this decision, so the explainer edit must describe the column as last-confirmed. The follow-up that adds the second column is what makes the original claim true.

### D13. `updated_at` is deliberately left alone, which changes two downstream behaviours for the better

**Decision.** The verified-touch does not bump `updated_at`. Three things read that column on entities, and all three improve as a result; none is mitigated.

**What reads it.** `list_entities` sorts by `updated_at DESC` (`catalog.py:136`), powering `/entities`. The admin UI renders it as a column in `EntityRow` and on the detail page, and the admin-ui spec's "Browse entities by source" scenario requires the list to display it. And `re-extract --since` filters chunks on `entity.updated_at >= $n` and orders by it (`reextract.py:127,142`).

**Effect on each.**

*The entity browser reorders.* It currently sorts by "last written", and since every ingest rewrites every row, that means the ordering after a full run is arbitrary within the run — every row shares a timestamp measured in the same few minutes. After this change the sort becomes "most recently changed", which is what an operator browsing a catalogue actually wants.

*The displayed column becomes accurate.* `updated_at` currently means "when we last overwrote this row", which is "when we last ingested". It will mean "when this content last changed" — which is what the name has always implied and never delivered.

*`re-extract --since` starts working.* Today the flag is close to inert: any ingest resets `updated_at` across the corpus, so `--since` matches nearly everything ingested after the date whether or not it changed. After this change it matches only genuinely changed content. This is a latent bug that the change fixes as a side effect.

**Alternatives rejected.** *Bump `updated_at` in the verified-touch to preserve current behaviour.* This perpetuates precisely the dishonesty the change is removing elsewhere, and keeps `--since` broken. *Re-sort the entity browser by `last_verified_at` to preserve the current ordering.* Preserves an ordering that was never meaningful.

**Risk.** All three shifts are silent. Nobody expects a change about avoiding redundant work to alter what the entities page lists first or which chunks `re-extract --since` selects. They are recorded as scenarios so they are tested and discoverable rather than discovered as bugs.

### D14. A skip touches the file's chunks too, in one statement, which requires an index

**Decision.** The verified-touch updates a skipped file's chunk rows as well as the parent, as a single `UPDATE ... WHERE tenant = $1 AND parent_entity_id = $2` per skipped file. This requires an index on `parent_entity_id`, which does not exist today.

**Rationale.** Chunk freshness is currently maintained by accident. Every ingest rewrites every chunk row, and `insert_entity` stamps `last_verified_at` as a side effect. Nothing ever set out to maintain that column; it was a byproduct of the redundant work this change removes. Take the rewriting away and the chunks freeze at whenever their file last changed.

That is not merely untidy. The background freshness sweep described in `add-foundation/specs/background-enrichment` selects rows by `last_verified_at`. Left alone, it would see a skipped file's chunks as six months unverified and queue them for re-checking minutes after ingestion confirmed them — spending its budget undoing the savings the gate just made.

A parent whose chunks disagree with it also violates the thin-MVP catalog-store contract, which states that every row tracks freshness and that chunks share their file's `source_revision`.

**Why one statement per file rather than one per chunk.** Touching chunks individually is a write per chunk — tens of thousands on a run that was supposed to be free. A single set-based update per skipped file is one round trip per file, which is negligible. The runner cannot enumerate chunk ids itself, because skipping means it never chunked the file and never derived them.

**The index, and the honest cost.** `opencg.entity` has no index on `parent_entity_id`; Postgres does not create one for a foreign key automatically. Without it, each bulk update sequentially scans the entity table, and 800 scans is worse than the per-chunk writes it replaces.

This weakens the "no schema change" property of this design, and that should be stated plainly rather than glossed. It is weakened, not lost: an index is not part of the data contract. Adding one changes no stored value and no query result, only speed, and its absence degrades performance rather than breaking writes — unlike a missing column. It can be added with `CREATE INDEX CONCURRENTLY IF NOT EXISTS` on a live database without locking the table.

The index is also already owed. `get_entity_with_lineage` selects a parent's children by `parent_entity_id` to render the admin entity detail page, and sequentially scans to do it today. This fixes an existing slow query rather than introducing a new requirement.

**Alternative rejected.** *Store the chunk id list in the marker,* making the touch a primary-key lookup and avoiding the index entirely. It works, but it puts tens of thousands of UUIDs into `metadata` across the corpus to duplicate information already derivable from the schema, and it inflates a marker whose job is to be small and cheap to read in bulk.

### D15. This change does not repair `bootstrap-thin-mvp`, whose ingestion spec cannot be archived as it stands

**Decision.** Our ingestion delta uses `ADDED`, and no attempt is made from inside this change to reconcile the contradicting requirement in `bootstrap-thin-mvp`. The reconciliation is a separate change.

**What was found.** `bootstrap-thin-mvp/specs/ingestion/spec.md` carries a `MODIFIED` requirement "Idempotency and content hashing" whose scenario triggers a skip on `content_hash` alone — precisely what D1 establishes is unsafe. Investigating the collision surfaced a larger, pre-existing problem.

That requirement originates as an `ADDED` block in `add-foundation`, which sits at 0 of 104 tasks and has never been archived. It has therefore never reached the baseline: `openspec/specs/ingestion/spec.md` holds six requirements and this is not among them. thin-MVP is modifying something that does not exist.

The same is true of three more of thin-MVP's six ingestion blocks. Its `MODIFIED` entries for *Confluence connector*, *Custom HTTP API connector*, and *Web indexer* all target requirements that live only in the unarchived `add-foundation`. Four of six dangle.

`openspec validate --strict` does not catch this. Both changes pass today. The validator checks a change's internal shape, not whether its `MODIFIED` targets exist in the baseline, so the failure would surface at archive time to whoever happens to be archiving.

**Why `ADDED` is right for us.** There is genuinely nothing in the baseline to modify. Had the requirement been archived, this change would have modified it instead.

**Why the repair is not ours.** It is four problems, of which our collision is one facet, and only one of the four is about incremental ingest at all. Fixing just ours would leave thin-MVP equally unarchivable while creating the impression it had been addressed. Nothing here blocks this change: it can be implemented and archived as written, and the four dangling blocks exist whether or not we ship. Archiving ours first does not worsen them.

**Recorded as** a follow-up task so it does not evaporate, in the same way as the bi-temporal work in D12.

## Risks / Trade-offs

- **A gate that skips too much is invisible.** → The skipped count is surfaced through the summary, the run store, `/runs/recent`, and the admin run history, and the staged rollout below provides a period where markers exist but nothing is skipped.
- **Silent permanent data loss is the failure mode, and code review is weak against it.** → Each of the four poison states from D1 gets an explicit test asserting the next run reprocesses, plus a fifth asserting a symbol-free file *is* skipped. That inverse case is the one most likely to be implemented backwards.
- **`IngestionSummary.__iter__` yields exactly two values and `server.py` destructures it inside a broad `except Exception`.** → A third value would turn every HTTP-triggered ingest into an opaque failure while the CLI and the smoke, which use attribute access, both pass. Either keep the arity or remove the iterator and convert both call sites.
- **The smoke asserts the ingest produced between 1 and 19 chunks.** → A second ingest that skips everything reports zero. The new assertions go in their own block before the existing tombstone step, leaving the current block untouched.
- **`chunker_version` could silently never change.** → Both existing call sites use `getattr(graphify, "__version__", "0.0.0")`. A silent default would defeat the invalidation the marker exists to provide, and graphifyy is pinned `>=0.8,<0.9`, so symbol-affecting patch bumps are permitted inside the pin. Resolve via `importlib.metadata.version` and fail loudly.
- **Two repositories whose URLs share a last path segment still share rows.** → Unchanged from today's behaviour, and harmless while nothing is deleted. It is a blocker for the deletion follow-up and belongs in that proposal.
- **`add-ontology-layer` touches adjacent code.** → D8 handles the semantic interaction; the two changes should still not be implemented concurrently.

## Migration Plan

No column migration. One index must exist before stage one ships — `CREATE INDEX CONCURRENTLY IF NOT EXISTS` on `opencg.entity (tenant, parent_entity_id)`, which does not lock the table, plus the same index in the init SQL for fresh databases. Deployment is otherwise staged so the behaviour change is separable from the machinery:

1. **Stage one — write markers, do not read them.** Ship the chunker outcome, the catalog methods, and the marker write with the gate disabled. Runs behave exactly as today and leave markers behind. Inspect real repositories: do the files expected to be complete carry markers, do symbol-free files carry `no_symbols`, does anything unexpected get marked?
2. **Stage two — enable the gate.** Now backed by observed evidence rather than reasoning, with the skipped count showing immediately if it over-skips.

**Rollback.** Stage two reverts by disabling the gate; markers left in metadata are inert when nothing reads them. Stage one reverts by ignoring the metadata key. Neither requires touching stored data.

**One-off cost.** The first run after stage two reprocesses the whole corpus, because no pre-existing row carries a marker. Document in `docs/OPERATIONS.md` alongside the invalidation procedure.

## Open Questions

- **Does `graphify.__version__` exist on the pinned distribution?** Both existing call sites guard it with `getattr(..., "0.0.0")`, and graphifyy is only installed inside the container, so this could not be confirmed while writing this design. It does not change the decision — D2 requires resolving the version through `importlib.metadata` and failing loudly either way — but the implementer should expect to discover that the attribute is missing and that the current default has been silently in effect.
- **The precise shape of `embedding_fingerprint`.** Provider, model, and vector dimension are the required components; whether they are stored as a structured object or a single derived string is an implementation choice to settle when the marker is first written.
