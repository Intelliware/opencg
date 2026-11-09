## 1. Catalogue lookup

- [ ] 1.1 Add `CatalogStore.live_entity_ids(tenant, ids) -> set[str]` (one `entity_id = ANY($2::uuid[]) AND tombstoned_at IS NULL` query; empty input returns without touching the pool)
- [ ] 1.2 Unit tests with the fake `_Pool`/`_Conn` pattern: SQL and args recorded, tombstoned and missing IDs excluded, empty-input short circuit

## 2. Dense leg of hybrid retrieval

- [ ] 2.1 In `stages/hybrid_retrieval.py`, over-fetch `min(2 × top_k, 200)` dense hits, drop those not in `live_entity_ids`, keep the first `top_k`, then fuse as today
- [ ] 2.2 Report `tombstoned_filtered` in the stage telemetry and set it on the `pipeline.hybrid_retrieval` span
- [ ] 2.3 Unit tests: a tombstoned dense hit never becomes a candidate; the live order is preserved; the lexical leg is unchanged

## 3. Admin vector search

- [ ] 3.1 Apply the same over-fetch and filter in `admin_routes.vector_search`; set `tombstoned_filtered` on the `pipeline.vector_search` span
- [ ] 3.2 Unit tests for the "Tombstoned entities are not returned" and "Filtering keeps up to top_k live hits" scenarios

## 4. End-to-end checks

- [ ] 4.1 Smoke: after the tombstone stage, call `/retrieve` again and fail if the tombstoned entity ID is in `fragments`
- [ ] 4.2 Turn the `entities.spec.ts` `test.fixme` ("a tombstoned chunk no longer appears in vector search") into a real test
- [ ] 4.3 Measure the added latency of the lookup on the reference stack and record it here

## 5. Verification

- [ ] 5.1 `make ci-static` and `make ci-stack` green
- [ ] 5.2 Update README known issues and `prepare-open-source-release` tasks.md 4.15
