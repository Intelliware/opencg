## MODIFIED Requirements

### Requirement: Change-driven enrichment

The system SHALL NOT run any change-driven enrichment worker in v0. A follow-up change MUST add the worker once the catalog event stream and graph extractor exist.

#### Scenario: No enrichment runs in v0

- **WHEN** an ingest event is published in the thin MVP
- **THEN** no enrichment worker consumes it because none are deployed

### Requirement: Freshness monitoring

The system SHALL NOT run a freshness sweep in v0. Catalog rows MUST remain at their ingestion-set `freshness_state` until a follow-up change adds the sweep worker.

#### Scenario: Freshness sweep is absent in v0

- **WHEN** a catalog row's `last_verified_at` exceeds any threshold
- **THEN** no automated transition to `stale` occurs because no sweep is deployed

### Requirement: Periodic relationship inference

The system SHALL NOT run periodic relationship inference in v0. The candidate-edge queue MUST be empty until the follow-up change that ships `knowledge-graph`.

#### Scenario: No candidate edges are produced in v0

- **WHEN** new content is ingested in the thin MVP
- **THEN** no candidate edges are written
- **AND** the candidate review queue surfaces nothing

### Requirement: Usage-feedback ingestion

The system SHALL NOT consume a usage-feedback stream in v0. The MCP `opencg/submit_feedback` tool MUST return `not_implemented_in_mvp` when called.

#### Scenario: Feedback submission rejected in v0

- **WHEN** an MCP client calls `opencg/submit_feedback`
- **THEN** the server returns `code = "not_implemented_in_mvp"`
- **AND** no row is written to any usage signals table

### Requirement: Feedback-driven re-ranking signal

The retrieval pipeline SHALL NOT consult any `usage_score` feature in v0. Future ranking changes that incorporate usage MUST be introduced through a follow-up change.

#### Scenario: No usage scores in v0

- **WHEN** the retrieval pipeline ranks candidates in the thin MVP
- **THEN** the ranking depends only on RRF over dense and lexical retrievers
- **AND** no `usage_score` column is read
