## MODIFIED Requirements

### Requirement: Seven-stage runtime path

The pipeline SHALL execute the contextual-layer stages for every retrieval request. The full v0 path is identity → intent classification → hybrid retrieval → catalog/graph lookup → rerank+compress → assemble+entitlement+audit → return.

In v0 the pipeline MUST execute four stages: identity, hybrid retrieval, assemble (collapsed: budget enforcement + permissive classification check + audit write), and return. Stages intent classification, catalog/graph lookup, and rerank+compress are deferred to follow-up changes that introduce the model adapters and graph. Every implemented stage MUST be independently observable as an OTel span.

#### Scenario: All thin-MVP stages run for a default query

- **WHEN** a query with no overrides is received in v0
- **THEN** the pipeline executes identity, hybrid retrieval, assemble, and return
- **AND** emits one child span per stage under the request's root trace

### Requirement: Intent-driven retrieval routing

In v0 the pipeline SHALL NOT call an intent classifier and SHALL run hybrid retrieval (dense + lexical, fused with RRF) with fixed weights on every request. The full routing surface MUST be added by the follow-up change that ships the intent classifier.

#### Scenario: Hybrid retrieval is the only plan in v0

- **WHEN** any retrieval request is received in the thin MVP
- **THEN** the pipeline runs vector and lexical search in parallel and fuses results with Reciprocal Rank Fusion
- **AND** no model is called for intent classification

### Requirement: Token-budgeted compression

In v0 the assemble stage SHALL enforce the caller-supplied token budget by dropping whole candidates in score order until the remaining set fits. The dedicated rerank+compress stage MUST be added by a follow-up change. No model MUST be invoked for compression in v0.

#### Scenario: Budget enforced by assemble

- **WHEN** the caller supplies a budget of 4000 tokens and the candidate set totals 12000 tokens
- **THEN** the assembled context contains at most 4000 tokens
- **AND** the audit record lists which candidates were dropped and why

### Requirement: Entitlement enforcement at assembly

In v0 the assemble stage SHALL enforce entitlement using a hardcoded role→classification allow-list and SHALL drop any candidate the principal is not entitled to see before returning. The OPA-backed enforcement MUST be added by a follow-up change without changing the per-candidate decision shape.

#### Scenario: Principal lacks entitlement in v0

- **WHEN** a retrieved candidate is classified `confidential:legal` and the principal does not have a role mapped to that classification
- **THEN** the candidate is excluded from the response
- **AND** the audit record contains the candidate ID and a `deny` decision with `reason = "classification_restricted"`

### Requirement: Deterministic recreatability

Given the same query, identity, model versions, and storage snapshot, the pipeline SHALL produce the same assembled context. The audit record MUST contain enough information to replay the request.

In v0 a replay endpoint MUST NOT be exposed. The audit record MUST still capture `model_versions`, ordered `candidate_ids`, and a `final_context_hash` computed deterministically from the kept fragments so a follow-up change can add the replay endpoint without changing the storage shape.

#### Scenario: Audit record contains a stable context hash

- **WHEN** a retrieval request completes
- **THEN** the audit row contains `final_context_hash` computed from the ordered list of kept `(entity_id, score, text)` tuples
- **AND** repeating the same request against the same storage state produces the same hash

### Requirement: Per-stage token accounting

Every stage that invokes a model SHALL record `model`, `tokens_in`, `tokens_out`, `latency_ms`, and `provider` on its span AND increment `opencg_tokens_total{stage,model,provider,tenant,direction}`.

In v0 only the hybrid retrieval stage invokes a model (embedding the query). It MUST set those attributes and increment the counter. Other stages MUST report zero token counts.

#### Scenario: Embeddings stage accounting

- **WHEN** the hybrid retrieval stage calls the embeddings provider for a query
- **THEN** the corresponding span has `model`, `provider`, `tokens_in`, `latency_ms` set
- **AND** the Prometheus counter increases by `tokens_in` for the embeddings model

## ADDED Requirements

### Requirement: Audit-read HTTP endpoints

The pipeline SHALL expose `GET /audit/recent?limit=N` and `GET /audit/{id}` returning JSON. These endpoints MUST be read-only and MUST NOT trigger any retrieval-side effects.

#### Scenario: List recent audits

- **WHEN** the admin UI calls `GET /audit/recent?limit=100`
- **THEN** the response is `{"items":[...]}` with at most 100 audit rows, ordered by `created_at desc`

#### Scenario: Fetch audit by id

- **WHEN** the admin UI calls `GET /audit/{id}` for an existing record
- **THEN** the response contains the full audit row
- **AND** an unknown id returns `404`
