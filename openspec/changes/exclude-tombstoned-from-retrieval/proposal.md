## Why

Tombstoning an entity is the only way an operator can withdraw content, and the admin UI tells them it "will be excluded from future retrievals". That is only half true. The lexical leg of hybrid retrieval reads Postgres and skips tombstoned rows, but the dense leg reads Qdrant, whose points are never touched by a tombstone. A tombstoned chunk therefore keeps coming back from `POST /retrieve`, and so reaches every MCP client, as well as from the admin `POST /search/vector`.

The archived catalog-store spec allowed this ("the Qdrant payload still contains the entity until a future change adds tombstone-aware vector cleanup"). The `prepare-open-source-release` e2e suite confirmed it on a live stack (tasks.md 4.7 and 4.15): a chunk tombstoned through the UI is still the top dense hit for its own text. Leaking withdrawn content to AI tools is not acceptable for a public release.

## What Changes

- Retrieval and admin vector search drop dense hits whose catalogue row is tombstoned, checking Postgres (the source of truth) at query time.
- The dense leg over-fetches from Qdrant so that filtering out tombstoned hits still leaves up to `top_k` results in the normal case.
- The filtered count is recorded on the existing retrieval and vector-search spans (`tombstoned_filtered`).
- The `prepare-open-source-release` e2e check for this (`entities.spec.ts`, currently `test.fixme`) becomes a real test, and the smoke test asserts that a tombstoned chunk is absent from a follow-up `/retrieve`.
- No Qdrant writes on tombstone, no schema change, no wire-type change.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `catalog-store`: the "Tombstoned rows are excluded from retrieval" scenario now covers both retrieval legs, not only `lexical_search`.
- `retrieval-pipeline`: `POST /search/vector` excludes tombstoned entities.

## Impact

- **Code:** `services/pipeline` only. That's a catalogue helper that returns the live subset of a list of entity IDs (one indexed query), used by the dense leg in `stages/hybrid_retrieval.py` and by `admin_routes.vector_search`.
- **Performance:** one extra indexed Postgres query per retrieval and per admin vector search. Qdrant returns up to twice `top_k` points, capped at 200.
- **Tests:** pipeline unit tests using the fake `_Pool`/`_Conn` pattern, the e2e `fixme` turned on, and a new smoke assertion.
- **Behaviour change for operators:** tombstoned content stops appearing in `/vectors` and in retrieval. Re-ingesting the source still restores it, as today.
- **Out of scope:** deleting Qdrant points on tombstone (storage cleanup), and cascading a parent's tombstone to its chunks (the catalog-store spec forbids cascade). Both are listed as open questions in design.md.
