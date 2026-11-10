## MODIFIED Requirements

### Requirement: OPA-backed entitlement policy

In v0 the pipeline SHALL enforce entitlement using a hardcoded role→classification allow-list rather than OPA. The decision record per candidate MUST use the same shape OPA will eventually produce (`{"entity_id":"…","decision":"allow|deny|drop","reason":"…"}`), so the follow-up change that wires OPA does not change the audit shape.

#### Scenario: Hardcoded policy denies access in v0

- **WHEN** a candidate's classification is not in the principal's role-derived allow-list
- **THEN** the candidate is excluded from the response
- **AND** the audit record contains `{"entity_id":"…","decision":"deny","reason":"classification_restricted"}` in `candidate_decisions`

### Requirement: Immutable, append-only audit log

Every assembled context SHALL produce an audit record in an append-only store. Audit records MUST NOT be mutable after write, except for an operator-only `legal_hold` flag that can be set but never cleared via the API.

In v0 `legal_hold` MAY be set only via direct DB access; the operator API for setting it is deferred.

#### Scenario: Cannot update an audit row

- **WHEN** any code path attempts to `UPDATE` a column of an audit row other than `legal_hold`
- **THEN** the database raises an error and the operation fails

### Requirement: Audit record content

An audit record SHALL include: `correlation_id`, `principal`, `roles`, `tenant`, `tool`, `query`, `intent_plan`, `retriever_versions`, `model_versions`, `vector_collection`, `vector_snapshot_id`, ordered `candidate_ids` with `candidate_decisions`, `final_entity_ids`, `final_context_hash`, `tokens_in`, `tokens_out`, `latency_ms`, `outcome`, and `created_at`.

In v0 `intent_plan` MUST be populated with `{"mvp":"hybrid_only"}` because intent classification is deferred. `vector_collection` and `vector_snapshot_id` MAY be `NULL` until the snapshot helper is wired up.

#### Scenario: Full record on every request

- **WHEN** a retrieval request completes
- **THEN** the audit row contains the required fields populated according to the thin-MVP scope above

### Requirement: Audit query API

The pipeline service SHALL expose only two audit endpoints in v0: `GET /audit/recent?limit=N` and `GET /audit/{id}`. Richer filters (by principal, by entity, by time range, by tool) MUST be added by a follow-up change.

#### Scenario: List recent audits via pipeline API

- **WHEN** the admin UI calls `GET /audit/recent?limit=50`
- **THEN** the response is `{"items":[...]}` with at most 50 rows ordered by `created_at desc`

#### Scenario: Fetch a single audit row

- **WHEN** the admin UI calls `GET /audit/{id}` for an existing record
- **THEN** the response contains the full audit row
- **AND** an unknown id returns `404`

### Requirement: Recreatability

In v0 the audit record SHALL contain everything required for a future replay endpoint: input `query`, `principal`, `roles`, `model_versions`, ordered `candidate_ids`, and `final_context_hash`. The replay HTTP endpoint itself MUST be added by a follow-up change without changing the storage shape.

#### Scenario: Audit record is replay-ready

- **WHEN** an audit record is written in v0
- **THEN** it contains `model_versions`, ordered `candidate_ids`, and a `final_context_hash`
- **AND** no replay endpoint is reachable on the pipeline service
