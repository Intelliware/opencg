## MODIFIED Requirements

### Requirement: Vector search HTTP endpoint

The pipeline service SHALL expose `POST /search/vector` accepting `{"query": <string>, "top_k"?: <int 1..100>, "filters"?: { … }}`. The endpoint MUST embed the query through the same embeddings client used by the retrieve path and MUST return `{"hits": [{ "entity_id", "score", "source", "source_uri", "title", "classification", "snippet" }], "model": "…", "provider": "…", "tokens_in": <int> }`.

The endpoint MUST NOT return hits whose catalogue entity is tombstoned. It SHALL over-fetch from the vector index (up to `min(2 × top_k, 200)` points), drop tombstoned hits using the catalog store's live-subset lookup, and return at most `top_k` hits. It MUST record the number of dropped hits as the `tombstoned_filtered` attribute of its span.

The endpoint MUST NOT write an audit row. It MUST emit an OTel span and increment the token counter as defined in the "Per-stage token accounting" requirement above.

#### Scenario: Vector search end-to-end

- **WHEN** a client calls `POST /search/vector` with `{"query":"prompt caching","top_k":10}`
- **THEN** the response contains up to 10 hits ordered by `score` desc
- **AND** the response carries the embedding `model`, `provider`, and `tokens_in`
- **AND** no row is written to `opencg.audit_log`

#### Scenario: Vector search top_k cap

- **WHEN** a client sends `top_k = 500`
- **THEN** the request is rejected with `400 Bad Request` and a message naming the 100 cap

#### Scenario: Tombstoned entities are not returned

- **WHEN** an entity is tombstoned and a client then searches with a query and filter that matched it before
- **THEN** no hit carries that `entity_id`
- **AND** the span's `tombstoned_filtered` attribute counts it

#### Scenario: Filtering keeps up to top_k live hits

- **WHEN** a client requests `top_k = 10`, 3 of the first 10 vector hits are tombstoned, and the first 20 vector hits include at least 10 live ones
- **THEN** the response contains 10 live hits, in score order
