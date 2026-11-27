## ADDED Requirements

### Requirement: OPA-backed entitlement policy

The system SHALL evaluate every assembled context candidate against an Open Policy Agent (OPA) decision endpoint with the input `{ principal, candidate, request }`. Decisions SHALL be cached for the lifetime of a single request only.

#### Scenario: Policy denies access

- **WHEN** OPA returns `{ allow: false, reason: "classification_restricted" }` for a candidate
- **THEN** the candidate is excluded from the assembled context
- **AND** the audit record contains the policy package, decision, and reason

### Requirement: Immutable, append-only audit log

Every assembled context SHALL produce an audit record in an append-only store. Audit records SHALL NOT be mutable after write, except for an operator-only legal-hold flag that can be set but never cleared via the API.

#### Scenario: Cannot update an audit row

- **WHEN** any code path attempts to `UPDATE` a column of an audit row other than `legal_hold`
- **THEN** the database raises an error and the operation fails

### Requirement: Audit record content

An audit record SHALL include: `correlation_id`, `principal`, `tenant`, `tool`, `query`, `intent_plan`, `retriever_versions`, `model_versions`, `vector_collection`, `vector_snapshot_id`, ordered `candidate_ids` with policy decision per candidate, `final_context_hash`, and `created_at`.

#### Scenario: Full record on every request

- **WHEN** a retrieval request completes
- **THEN** the audit row contains all required fields populated

### Requirement: Audit query API

The system SHALL expose an admin API to query audit records by correlation ID, principal, time range, entity ID, and tool. Results SHALL include the full record and a link to a "replay" preview.

#### Scenario: Operator searches by entity

- **WHEN** an operator queries audit records by `entity_id = E1` for a week range
- **THEN** all audit rows where `E1` appeared in `candidate_ids` (regardless of final inclusion) are returned

### Requirement: Recreatability

A "replay" action SHALL reconstruct the assembled context for an audit record using stored model versions, snapshots, and the original input, and SHALL flag any divergence.

#### Scenario: Replay matches original

- **WHEN** an operator triggers replay on a recent audit record where snapshots are still available
- **THEN** the reconstructed context hash equals `final_context_hash`
- **AND** divergence is reported when a snapshot has been pruned
