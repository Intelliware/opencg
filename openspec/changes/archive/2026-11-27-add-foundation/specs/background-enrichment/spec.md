## ADDED Requirements

### Requirement: Change-driven enrichment

The system SHALL subscribe to ingestion events and, within seconds of a document change, trigger re-embedding and relationship-extraction jobs for the affected entities.

#### Scenario: Event triggers enrichment

- **WHEN** an `IngestEvent` of type `document_updated` is published
- **THEN** an enrichment job for that entity is enqueued and starts within five seconds under normal load

### Requirement: Freshness monitoring

A periodic worker SHALL sweep the catalog at a configured cadence (default hourly), select rows whose `last_verified_at` exceeds the per-source freshness threshold, and dispatch verification jobs that recompute `content_hash` or re-fetch metadata.

#### Scenario: Freshness sweep

- **WHEN** the freshness worker runs
- **THEN** stale rows are queued for verification
- **AND** verification results update `last_verified_at` and `freshness_state`

### Requirement: Periodic relationship inference

A daily worker SHALL run relationship inference over recently changed entities and across the global graph at a slower cadence (default weekly), producing candidate edges via the configured extractor.

#### Scenario: Nightly run

- **WHEN** the nightly relationship inference completes
- **THEN** new candidate edges are visible in the admin UI's review queue

### Requirement: Usage-feedback ingestion

The system SHALL consume the usage-feedback stream produced by the MCP server (`submit_feedback`, click-throughs, downstream model outcomes when reported) and persist signals to the catalog as `usage_signals` rows tied to `entity_id` and `correlation_id`.

#### Scenario: Feedback persisted

- **WHEN** a `submit_feedback` event arrives
- **THEN** a `usage_signals` row is written with `rating`, `notes`, `correlation_id`, and `entity_ids`

### Requirement: Feedback-driven re-ranking signal

Persisted usage signals SHALL feed into a per-entity `usage_score` updated by a periodic aggregation job, and the retrieval pipeline's rerank stage SHALL incorporate `usage_score` as a feature.

#### Scenario: Useful documents rise

- **WHEN** a document receives repeated `useful` ratings across distinct correlation IDs
- **THEN** its `usage_score` increases
- **AND** future rerank calls give it a higher final score, all else equal
