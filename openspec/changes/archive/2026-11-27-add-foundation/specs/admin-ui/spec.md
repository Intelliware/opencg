## ADDED Requirements

### Requirement: Query review

The admin UI SHALL list recent MCP queries with `correlation_id`, `principal`, `tool`, `query`, `latency_ms`, `tokens`, `cost_usd`, and `outcome`. Filters SHALL include time range, principal, tool, and outcome. Selecting a row SHALL show the full audit record and the assembled context.

#### Scenario: Operator inspects a query

- **WHEN** an operator opens a row from the query review list
- **THEN** the UI shows the audit record, per-stage timings/tokens, retrieved candidates with policy decisions, and the final assembled context

### Requirement: Returned-context inspection

The UI SHALL display the assembled context exactly as returned to the MCP client, with per-fragment metadata (source, score, tokens, classification) and a copy-as-JSON action.

#### Scenario: View returned context

- **WHEN** the operator views the returned context for a request
- **THEN** they see the ordered fragments with metadata and can copy the raw JSON

### Requirement: Graph relationship management

The UI SHALL provide an interface to browse confirmed and candidate edges, search for entities, view neighbours, and create/edit/promote/delete edges. Bulk operations SHALL be supported on the candidate review queue.

#### Scenario: Review queue triage

- **WHEN** an admin opens the candidate review queue
- **THEN** they see candidate edges ordered by confidence with `entity_from`, `entity_to`, `type`, `confidence`, `evidence_uri`, and bulk-promote/reject actions

#### Scenario: Edit an edge

- **WHEN** an admin changes a confirmed edge's `type`
- **THEN** the change is persisted with an audit row recording the actor and prior value

### Requirement: Vector neighbourhood exploration

The UI SHALL allow an operator to query Qdrant for the nearest neighbours of an entity or an ad-hoc query string and SHALL render a 2D projection of a chosen neighbourhood (UMAP) for visual review.

#### Scenario: Inspect neighbours of an entity

- **WHEN** an operator opens an entity and clicks "show neighbours"
- **THEN** the UI shows the top-K nearest vectors with scores
- **AND** an option to render a UMAP projection of the surrounding cluster

### Requirement: Content management

The UI SHALL allow operators to view individual entities (raw text, metadata, lineage), tombstone entities, re-trigger embedding/relationship extraction per entity, and view freshness state.

#### Scenario: Re-extract relationships

- **WHEN** an operator triggers re-extraction on an entity
- **THEN** a relationship-extraction job is enqueued and the UI shows its progress

### Requirement: Content ingestion control

The UI SHALL list configured connectors with `status`, `last_run`, `next_run`, `error_count`, allow operators to trigger an ad-hoc run, and SHALL provide a "ingest URL" panel that submits a single URL to the web indexer (subject to allow-list policy).

#### Scenario: Trigger connector

- **WHEN** an operator clicks "Run now" on a connector
- **THEN** the connector is dispatched and the UI tracks the new job
