## Context

Hybrid retrieval (`stages/hybrid_retrieval.py`) runs two legs in parallel. The dense leg embeds the query and calls `VectorIndex.search`, building candidates straight from the Qdrant payload. The lexical leg calls `CatalogStore.lexical_search`, which filters `tombstoned_at IS NULL`. The results are fused with RRF. `POST /search/vector` calls `VectorIndex.search_all` and returns payloads directly.

`DELETE /entities/{id}` sets `tombstoned_at` on the Postgres row only. Nothing updates Qdrant. Verified on a live stack during `prepare-open-source-release`: a tombstoned chunk was returned by both `/search/vector` (filtered to its source) and `/retrieve`.

## Goals / Non-Goals

**Goals:**
- A tombstoned entity never appears in `/retrieve` fragments or in `/search/vector` hits.
- The fix holds even if Qdrant and Postgres disagree, for example after a failed or partial write.
- No new write path, migration or wire-type change.

**Non-Goals:**
- Reclaiming Qdrant storage for tombstoned points.
- Cascading a parent's tombstone to its chunks.
- Exposing tombstoned hits to admins on request (no `include_tombstoned` flag in this change).

## Decisions

### D1. Filter at query time against Postgres

After the dense search, the pipeline asks the catalogue which of the returned entity IDs are live:

```sql
SELECT entity_id::text FROM opencg.entity
WHERE tenant = $1 AND entity_id = ANY($2::uuid[]) AND tombstoned_at IS NULL
```

It then drops every hit not in that set. Postgres already owns tombstone state, so one indexed primary-key lookup per request makes it authoritative for both legs.

*Alternatives:*
- **Delete the Qdrant points on tombstone.** This reclaims space, but it makes tombstoning a two-store write. If the Qdrant delete fails after the Postgres update, the leak returns silently, so query-time filtering would still be needed as the guarantee. It's a possible later cleanup, not the fix.
- **Set a `tombstoned` payload flag and filter in Qdrant.** This has the same two-store consistency problem, plus a payload-index requirement.

### D2. Over-fetch so filtering rarely costs results

The dense leg asks Qdrant for `min(2 × top_k, 200)` points, filters them, and keeps the first `top_k`. When more than half of the over-fetched hits are tombstoned, fewer than `top_k` dense hits come back. That is acceptable: the lexical leg still contributes, and returning withdrawn content would be worse. RRF ranks within the fused list, so over-fetching does not change the relative order of the live hits.

### D3. One helper shared by both callers

`CatalogStore.live_entity_ids(tenant, ids) -> set[str]` is used by the dense leg and by `admin_routes.vector_search`. An empty input returns an empty set without touching the database. The vector-index wrapper stays storage-agnostic, so no Postgres dependency is added to `storage/vector.py`.

### D4. Observability

The `pipeline.hybrid_retrieval` and `pipeline.vector_search` spans get a `tombstoned_filtered` integer attribute. No new Prometheus metric: this is not a model call, so the token-accounting rule does not apply.

## Risks / Trade-offs

- **An extra query on the hot path.** It's a primary-key `ANY` lookup over at most 200 UUIDs, so it should add well under a millisecond on the reference stack. It will be measured during implementation and recorded in tasks.md.
- **Heavily tombstoned corpora return fewer dense hits.** This is mitigated by over-fetching. If it matters later, D1's storage-cleanup alternative removes the cause.
- **Ingestion re-upserts.** Re-ingesting a tombstoned source clears `tombstoned_at` (existing behaviour, `catalog.py`), and the hit comes back as expected.

## Open Questions

1. Should tombstoning a parent document also hide its chunks from retrieval? Today the catalog-store spec says tombstoning "MUST NOT cascade", and chunks of a tombstoned parent are still retrievable through both legs.
2. Should a later change delete Qdrant points for tombstoned entities to reclaim space (D1 alternative), for example as a periodic sweep?
