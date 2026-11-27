## ADDED Requirements

### Requirement: Seven-stage runtime path

For every retrieval request, the pipeline SHALL execute the following stages in order: (1) Identity, (2) Intent classification, (3) Hybrid retrieval, (4) Catalog/graph lookup, (5) Rerank + compress, (6) Assemble + entitlement check, (7) Return. Each stage SHALL be independently observable and skippable only when a routing rule from stage 2 explicitly disables it.

#### Scenario: All stages run for a default query

- **WHEN** a query with no routing overrides is received
- **THEN** the pipeline executes all seven stages
- **AND** emits one child span per stage under the request's root trace

#### Scenario: Intent classifier disables a stage

- **WHEN** the intent classifier returns `route = direct_query_only`
- **THEN** the pipeline skips vector search and rerank
- **AND** the skipped stages emit a span with `status = skipped` and a `reason` attribute

### Requirement: Intent-driven retrieval routing

Stage 2 SHALL classify the query intent and produce a `RetrievalPlan` that names which retrievers run (`vector`, `bm25`, `catalog`, `graph`, `direct_query`) and the fusion weights. The pipeline SHALL execute the plan as specified.

#### Scenario: Plan selects hybrid retrieval

- **WHEN** the intent classifier returns `plan = { retrievers: ["vector","bm25"], fusion: "rrf", weights: { vector: 0.6, bm25: 0.4 } }`
- **THEN** stage 3 runs vector and BM25 in parallel and fuses results with Reciprocal Rank Fusion using the supplied weights

### Requirement: Token-budgeted compression

Stage 5 SHALL drop low-signal candidates and compress retained candidates to fit a token budget supplied by the caller. The stage MUST NOT exceed the supplied budget and SHOULD prefer dropping whole documents over truncating critical metadata.

#### Scenario: Budget enforced

- **WHEN** the caller supplies a budget of 4000 tokens and the candidate set totals 12000 tokens
- **THEN** the assembled context contains at most 4000 tokens
- **AND** the audit record lists which candidates were dropped and why

### Requirement: Entitlement enforcement at assembly

Stage 6 SHALL evaluate every retained candidate against the entitlement policy using the request identity, and SHALL drop any candidate the principal is not entitled to see before returning. Dropped candidates SHALL appear in the audit record with the policy decision.

#### Scenario: Principal lacks entitlement

- **WHEN** a retrieved document is classified `confidential:legal` and the principal does not have the `legal` role
- **THEN** the document is excluded from the response
- **AND** the audit record contains the document ID, the policy package consulted, and the `deny` decision

### Requirement: Deterministic recreatability

Given the same query, identity, model versions, and storage snapshot, the pipeline SHALL produce the same assembled context. The audit record SHALL contain everything required to replay the request: input query, identity, model adapter versions, retriever versions, snapshot identifiers, and the ordered list of retained candidate IDs.

#### Scenario: Replay reconstructs the context

- **WHEN** an operator replays an audited request against the same storage snapshot
- **THEN** the resulting context is byte-identical to the original

### Requirement: Per-stage token accounting

Every stage that invokes a model SHALL record `model`, `tokens_in`, `tokens_out`, `latency_ms`, and `provider` on its span and write a counter increment under `opencg_tokens_total{stage,model,provider,tenant}`.

#### Scenario: Embeddings stage accounting

- **WHEN** stage 3 calls the embeddings provider for a query
- **THEN** the corresponding span has the four attributes set
- **AND** the Prometheus counter increases by `tokens_in` for the embeddings model
