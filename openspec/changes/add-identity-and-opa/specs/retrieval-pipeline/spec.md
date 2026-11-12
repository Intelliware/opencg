## ADDED Requirements

### Requirement: Request identity derivation

The pipeline SHALL derive the identity of every request through one shared dependency. In `oidc` mode it MUST validate the bearer token and map its claims to `IdentityContext`; the `identity` object in a `/retrieve` body MUST be ignored. In `none` mode it MUST use the identity from the request body when present and the configured stub identity otherwise. Stage 1 (identity) MUST record `principal`, `tenant` and `auth_method` on its span.

#### Scenario: Token identity wins over the body

- **WHEN** in `oidc` mode a request authenticated as `bob` posts `/retrieve` with `identity.roles = ["admin","legal"]`
- **THEN** entitlement is evaluated with `bob`'s token roles, not the body's roles

#### Scenario: Stage span carries identity

- **WHEN** any `/retrieve` call completes
- **THEN** the `pipeline.identity` span has `principal`, `tenant` and `auth_method` attributes

### Requirement: Entitlement enforcement at assembly

The retrieval path SHALL run an entitle stage (span `pipeline.entitle`) between hybrid retrieval and assemble. It MUST send all candidates to the `opencg.entitlement` policy in one request, remove every denied candidate, and only then apply the token budget, so denied candidates never consume budget. The span MUST record `candidates_in`, `denied`, `policy_revision` and `latency_ms`. The assemble stage MUST NOT contain role or classification rules of its own.

#### Scenario: Principal lacks entitlement

- **WHEN** a retrieved document is classified `confidential:legal` and the principal does not have the `legal` role
- **THEN** the document is excluded from the response
- **AND** the audit record contains the document ID, the policy package consulted, the policy revision and the `deny` decision

#### Scenario: Denied candidates do not use the budget

- **WHEN** the top-scored candidate is denied and the remaining candidates fit the budget only without it
- **THEN** the response includes the remaining allowed candidates up to the budget

#### Scenario: One policy call per request

- **WHEN** a `/retrieve` call produces 40 candidates
- **THEN** the pipeline sends exactly one request to the OPA entitlement endpoint

### Requirement: API action authorization

Every pipeline route other than `/healthz`, `/readyz` and `/metrics` SHALL map to exactly one action (`retrieve`, `search.vector`, `audit.read`, `entity.read`, `entity.tombstone`, `graph.read`, `graph.write`, `vocab.write`, `ingestion.read`, `ingestion.run`) and MUST be authorized by the `opencg.admin` policy before its handler runs. A deny MUST return `403` with `code = "forbidden"` and the policy's reason, without performing the action.

#### Scenario: Reader cannot edit the graph

- **WHEN** a principal with roles `["reader"]` calls `POST /graph/edges/{id}/promote`
- **THEN** the response is `403` with `code = "forbidden"`
- **AND** the edge's state is unchanged and no `graph_audit_log` row is written

#### Scenario: Unmapped route fails the build

- **WHEN** a contributor adds a pipeline route without an action mapping
- **THEN** the route-coverage unit test fails and names the route

### Requirement: Default action permissions

The default `opencg.admin` policy SHALL grant `reader` the actions `retrieve`, `search.vector` and every `*.read` action, and MUST grant `admin` every action. Any action the policy does not know MUST be denied.

#### Scenario: Reader can browse

- **WHEN** a principal with roles `["reader"]` calls `GET /graph/concepts`
- **THEN** the response is `200`

#### Scenario: Admin can tombstone

- **WHEN** a principal with roles `["admin"]` calls `DELETE /entities/{id}` for a current-run entity
- **THEN** the entity is tombstoned

## MODIFIED Requirements

### Requirement: Vector search HTTP endpoint

The pipeline service SHALL expose `POST /search/vector` accepting `{"query": <string>, "top_k"?: <int 1..100>, "filters"?: { … }}`. The endpoint MUST embed the query through the same embeddings client used by the retrieve path and MUST return `{"hits": [{ "entity_id", "score", "source", "source_uri", "title", "classification", "snippet" }], "model": "…", "provider": "…", "tokens_in": <int> }`.

The endpoint MUST NOT return hits whose catalogue entity is tombstoned. It SHALL over-fetch from the vector index (up to `min(2 × top_k, 200)` points), drop tombstoned hits using the catalog store's live-subset lookup, and return at most `top_k` hits. It MUST record the number of dropped hits as the `tombstoned_filtered` attribute of its span.

The endpoint MUST NOT return hits the caller is not entitled to. After the tombstone filter, it MUST submit the remaining hits to the `opencg.entitlement` policy in one request with the caller's identity, drop denied hits, and record their number as the `entitlement_filtered` attribute of its span. When the policy is unavailable it MUST respond `503` with `code = "policy_unavailable"`.

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

#### Scenario: Entitlement filters vector hits

- **WHEN** a principal without the `legal` role searches with a query that matches a `confidential:legal` entity
- **THEN** no hit carries that `entity_id`
- **AND** the span's `entitlement_filtered` attribute counts it

### Requirement: Graph admin write endpoints

The pipeline service SHALL expose graph admin write endpoints. Each MUST be idempotent where the operation is semantically idempotent (re-promoting an already-confirmed edge is a no-op), and every state transition MUST persist a row in `opencg.graph_audit_log`. The row's `actor` MUST be the principal of the authenticated request (the stub principal in `none` mode), never a value read from configuration in `oidc` mode.

- `POST /graph/concepts/{id}/promote` — `{reason?}` → `state = confirmed`.
- `POST /graph/concepts/{id}/demote` — `{reason?}` → `state = candidate`.
- `DELETE /graph/concepts/{id}` — `{reason?}` → `state = tombstoned`.
- `POST /graph/concepts/merge` — `{into_id, from_ids[], reason?}` re-points edges, tombstones the merged-from concepts, and appends their aliases.
- `PATCH /graph/concepts/{id}` — `{name?, description?, aliases?}` updates editable fields.
- `POST /graph/edges/{id}/promote` — same shape as concepts.
- `POST /graph/edges/{id}/demote` — same shape.
- `DELETE /graph/edges/{id}` — tombstone.
- `PATCH /graph/edges/{id}` — `{type?, from_concept_id?, to_concept_id?}` edit endpoints or type.
- `POST /graph/vocab` — `{name, description?, inverse?, directed?}` add a relationship type.
- `PATCH /graph/vocab/{name}` — edit description / inverse / directed.
- `POST /graph/vocab/{name}/deprecate` — mark deprecated.

#### Scenario: Promotion writes audit row

- **WHEN** a client authenticated as `alice` calls `POST /graph/concepts/{id}/promote` with `{reason:"reviewed"}`
- **THEN** the concept's `state` becomes `confirmed`
- **AND** a `graph_audit_log` row is written with `target_kind="concept"`, `from_state="candidate"`, `to_state="confirmed"`, `actor="alice"`, `reason="reviewed"`, and `before` / `after` snapshots

#### Scenario: Merging concepts re-points edges

- **WHEN** an admin calls `POST /graph/concepts/merge` with `{into_id:"A", from_ids:["B","C"], reason:"…"}`
- **THEN** every edge whose endpoint is `B` or `C` is re-pointed to `A`
- **AND** `B` and `C` are tombstoned
- **AND** their aliases are appended to `A.aliases` (deduped)

#### Scenario: Vocabulary insertion of a deprecated name fails

- **WHEN** an admin calls `POST /graph/vocab` with `{name:"causes"}` and `causes` is already deprecated
- **THEN** the response is `409 Conflict` with `code="vocab_name_in_use"`

#### Scenario: Stub actor in open mode

- **WHEN** the auth mode is `none` and a client promotes a concept
- **THEN** the `graph_audit_log` row's `actor` is the configured stub principal

### Requirement: Ingestion control proxies

The pipeline service SHALL proxy three endpoints to the ingestion service over the compose network: `GET /ingestion/connectors`, `POST /ingestion/git/run`, and `GET /ingestion/runs/recent`. Failures from the ingestion service MUST surface as `502 Bad Gateway` with the upstream body included.

The pipeline MUST NOT cache responses; the proxy is a thin pass-through so cross-cutting concerns (OPA, rate limit) have a single attach point. Each proxied call MUST be authorized as `ingestion.read` or `ingestion.run` before it is forwarded, and in `oidc` mode MUST forward the caller's bearer token so the ingestion service can authenticate and authorize it independently. Upstream `401` and `403` responses MUST be returned to the caller unchanged rather than as `502`.

#### Scenario: Proxy connectors list

- **WHEN** a client calls `GET /ingestion/connectors` against the pipeline
- **THEN** the pipeline forwards to `GET /connectors` on the ingestion service
- **AND** the response body matches the ingestion service's response

#### Scenario: Proxy run request

- **WHEN** a client calls `POST /ingestion/git/run` with `{"repo_url":"https://…"}`
- **THEN** the pipeline forwards to `POST /run/git` on the ingestion service with the same body
- **AND** the response contains `{run_id, status}`

#### Scenario: Upstream failure surfaces as 502

- **WHEN** the ingestion service returns `500` to a proxied request
- **THEN** the pipeline returns `502 Bad Gateway` with the upstream body included in the error payload

#### Scenario: Reader cannot start a run

- **WHEN** a principal with roles `["reader"]` calls `POST /ingestion/git/run`
- **THEN** the pipeline returns `403` without contacting the ingestion service
