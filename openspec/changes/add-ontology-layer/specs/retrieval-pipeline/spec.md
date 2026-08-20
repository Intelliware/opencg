## MODIFIED Requirements

### Requirement: Graph read endpoints

The pipeline service SHALL expose graph read endpoints used by the admin UI and the MCP `traverse_graph` tool:

- `GET /graph/concepts?state&search&include_tombstoned&limit&offset` — paginated browse with filters. `state` accepts a comma-separated set of `candidate|confirmed`. `search` is a case-insensitive name substring match. Defaults: `state=confirmed,candidate`, `include_tombstoned=false`, `limit=50` (max 200), `offset=0`.
- `GET /graph/concepts/{concept_id}` — single concept plus its immediate neighbours (confirmed + candidate, each with the connecting edge metadata).
- `GET /graph/traverse?concept_id=&types=&classes=&depth=&limit=&include_candidates=&include_violations=` — see the knowledge-graph spec for full semantics.
- `GET /graph/vocab` — **deprecated.** Superseded by `GET /ontology/relationships` now that the vocabulary belongs to the ontology. It MUST keep returning the same payload for one release and MUST mark itself deprecated.
- `GET /graph/edges?state&type&limit&offset` — paginated edge browse used by the candidate review queue.

All endpoints MUST be read-only (no audit-row write side effects).

#### Scenario: List concepts with filters

- **WHEN** a client calls `GET /graph/concepts?state=candidate&search=prompt&limit=10`
- **THEN** the response is `{items:[…], total:<int>, limit:10, offset:0}` listing concepts in `candidate` state whose name contains "prompt" (case-insensitive)

#### Scenario: Concept detail with neighbours

- **WHEN** a client calls `GET /graph/concepts/{id}` for a concept that has 3 confirmed and 2 candidate edges
- **THEN** the response contains the concept plus `neighbours: { confirmed: […], candidate: […] }` with the edge metadata (type, confidence, evidence_uris) on each entry

#### Scenario: Edge browse paginated

- **WHEN** a client calls `GET /graph/edges?state=candidate&limit=20`
- **THEN** the response is `{items:[…], total:<int>}` with at most 20 candidate edges ordered by `confidence DESC, created_at DESC`

#### Scenario: Deprecated vocabulary read still answers

- **WHEN** a client calls `GET /graph/vocab`
- **THEN** the payload matches `GET /ontology/relationships`
- **AND** the response marks the path deprecated

### Requirement: Graph admin write endpoints

The pipeline service SHALL expose graph admin write endpoints. Each MUST be idempotent where the operation is semantically idempotent (re-promoting an already-confirmed edge is a no-op), and every state transition MUST persist a row in `opencg.graph_audit_log`.

- `POST /graph/concepts/{id}/promote` — `{reason?}` → `state = confirmed`.
- `POST /graph/concepts/{id}/demote` — `{reason?}` → `state = candidate`.
- `DELETE /graph/concepts/{id}` — `{reason?}` → `state = tombstoned`.
- `POST /graph/concepts/merge` — `{into_id, from_ids[], reason?}` re-points edges, tombstones the merged-from concepts, and appends their aliases.
- `PATCH /graph/concepts/{id}` — `{name?, description?, aliases?, class_id?}` updates editable fields. Changing `class_id` MUST NOT change the concept's `state`.
- `POST /graph/edges/{id}/promote` — same shape as concepts.
- `POST /graph/edges/{id}/demote` — same shape.
- `DELETE /graph/edges/{id}` — tombstone.
- `PATCH /graph/edges/{id}` — `{type?, from_concept_id?, to_concept_id?}` edit endpoints or type.

The relationship-vocabulary writes formerly served here — `POST /graph/vocab`, `PATCH /graph/vocab/{name}`, and `POST /graph/vocab/{name}/deprecate` — MOVE to `/ontology/relationships` because the vocabulary is now an ontology object. The `/graph/vocab` paths MUST continue to work as deprecated aliases for one release, preserving their existing status codes and error codes, and MUST be removed in the follow-up that archives this change.

#### Scenario: Promotion writes audit row

- **WHEN** a client calls `POST /graph/concepts/{id}/promote` with `{reason:"reviewed"}`
- **THEN** the concept's `state` becomes `confirmed`
- **AND** a `graph_audit_log` row is written with `target_kind="concept"`, `from_state="candidate"`, `to_state="confirmed"`, `actor` derived from the identity stub, `reason="reviewed"`, and `before` / `after` snapshots

#### Scenario: Merging concepts re-points edges

- **WHEN** an admin calls `POST /graph/concepts/merge` with `{into_id:"A", from_ids:["B","C"], reason:"…"}`
- **THEN** every edge whose endpoint is `B` or `C` is re-pointed to `A`
- **AND** `B` and `C` are tombstoned
- **AND** their aliases are appended to `A.aliases` (deduped)

#### Scenario: Vocabulary insertion of a deprecated name fails

- **WHEN** an admin calls `POST /ontology/relationships` with `{name:"causes"}` and `causes` is already deprecated
- **THEN** the response is `409 Conflict` with `code="vocab_name_in_use"`

#### Scenario: Deprecated vocabulary write still works for one release

- **WHEN** an admin calls the legacy `POST /graph/vocab`
- **THEN** the relationship type is created exactly as `POST /ontology/relationships` would create it
- **AND** the audit row records `target_kind = "ontology_relationship"`

## ADDED Requirements

### Requirement: Ontology endpoints on the pipeline service

The pipeline SHALL serve the ontology admin API under `/ontology/...`, following the module and routing pattern already established by `/graph/...`. The route set covers class read, create, update, and deprecate; constraint list, create, and delete; and a re-check trigger that re-evaluates `constraint_state` for a named relationship type.

These routes are administrative and sit behind the same (currently absent) authentication posture as the rest of the admin surface; this change MUST NOT claim to add authentication it does not implement.

Browser access MUST go through Next route handlers under `src/app/api/proxy/...`, consistent with every other admin surface, because the pipeline URL is compose-internal.

#### Scenario: Ontology routes are served by the pipeline

- **WHEN** a caller requests `GET /ontology/classes` against the pipeline
- **THEN** the ontology class tree is returned

#### Scenario: Admin UI reaches ontology routes through the proxy

- **WHEN** the ontology page loads in a browser
- **THEN** its requests go to Next route handlers under `/api/proxy/...`
- **AND** no browser request targets the compose-internal pipeline URL directly

#### Scenario: Re-check can be triggered for one relationship type

- **WHEN** an operator posts a re-check for a named relationship type
- **THEN** edges of that type are re-evaluated and their `constraint_state` values updated
- **AND** no edge's review `state` changes

### Requirement: Ontology observability

The extraction span `pipeline.graph_extract` SHALL carry an `ontology_version` attribute identifying the ontology state the prompt was generated from, so a change in extraction quality can be attributed to a schema edit. Constraint evaluation SHALL increment `opencg_constraint_violations_total{relation,domain_class,range_class}` on every verdict of `violation`.

Per-stage token accounting for the extraction stage MUST continue to emit both the OTel span attribute and the `opencg_tokens_total{stage,model,provider,tenant,direction}` increment; generating the prompt from the ontology MUST NOT bypass either.

#### Scenario: Extraction span names the ontology version

- **WHEN** a chunk is extracted
- **THEN** the `pipeline.graph_extract` span carries an `ontology_version` attribute

#### Scenario: Violations are counted with their classes

- **WHEN** an edge is evaluated as a violation
- **THEN** `opencg_constraint_violations_total` increments with the relation, domain class, and range class as labels

#### Scenario: Token accounting survives generated prompts

- **WHEN** extraction runs with an ontology-generated prompt
- **THEN** the span records token counts
- **AND** `opencg_tokens_total` increments for both directions
