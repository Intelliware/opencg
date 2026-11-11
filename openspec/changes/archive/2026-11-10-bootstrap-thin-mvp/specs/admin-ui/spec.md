## MODIFIED Requirements

### Requirement: Query review

The admin UI SHALL list recent MCP queries with `correlation_id`, `principal`, `tool`, `query`, `latency_ms`, `tokens`, and `outcome`. Selecting a row SHALL show the full audit record.

In v0 the list MUST be unfiltered and ordered by `created_at desc`. Filters (time range, principal, tool, outcome) and `cost_usd` are deferred to a follow-up change.

#### Scenario: Operator inspects a query

- **WHEN** an operator opens `/queries/{id}` from the query review list
- **THEN** the UI shows the audit record including `correlation_id`, `tenant`, `principal`, `roles`, `tool`, `query`, candidate IDs, final entity IDs, `final_context_hash`, latency, and token usage

### Requirement: Returned-context inspection

The UI SHALL display the assembled context exactly as returned to the MCP client, with per-fragment metadata and a copy-as-JSON action.

In v0 the audit detail page MUST list final entity IDs only. The full fragments view (per-fragment text, score, tokens) and the copy-as-JSON action are deferred. The audit record on the pipeline side already carries `final_entity_ids` and `final_context_hash` so the follow-up change can render the fragments without storage changes.

#### Scenario: View final entity IDs

- **WHEN** the operator views the audit detail page
- **THEN** the page lists each final entity ID

### Requirement: Graph relationship management

The admin UI SHALL NOT expose any graph relationship management surface in v0. The follow-up change that ships `knowledge-graph` MUST add this surface.

#### Scenario: Graph management is absent in v0

- **WHEN** an operator navigates the admin UI in the thin MVP
- **THEN** no graph relationship management route is reachable and no graph CRUD API is called

### Requirement: Vector neighbourhood exploration

The admin UI SHALL NOT expose vector-neighbourhood exploration in v0. A follow-up change MUST add it.

#### Scenario: Vector exploration is absent in v0

- **WHEN** an operator navigates the admin UI in the thin MVP
- **THEN** no vector neighbourhood route is reachable

### Requirement: Content management

The admin UI SHALL NOT expose entity-level content management in v0. A follow-up change MUST add it.

#### Scenario: Content management is absent in v0

- **WHEN** an operator navigates the admin UI in the thin MVP
- **THEN** no entity detail / tombstone / re-extract surface is reachable

### Requirement: Content ingestion control

The admin UI SHALL NOT expose connector control in v0. Operators MUST trigger ingestion via the `opencg-ingest` CLI in v0; a follow-up change adds the UI surface.

#### Scenario: Ingestion control is absent in v0

- **WHEN** an operator navigates the admin UI in the thin MVP
- **THEN** no connector list, no "run now", and no "ingest URL" panel is reachable

## ADDED Requirements

### Requirement: Storybook scaffold

The admin UI SHALL ship a Storybook configuration. Every shared component (`QueryRow`, `TokenBar`, `AuditRecordView` in v0) MUST have at least one neighbour `*.stories.tsx` file. New components added in future changes MUST be added to Storybook in the same change that introduces them.

#### Scenario: Storybook starts without error

- **WHEN** an operator runs `pnpm --filter @opencg/admin-ui storybook`
- **THEN** Storybook starts on port 6006 and renders the v0 stories

#### Scenario: Components used in app routes also exist as stories

- **WHEN** a component is consumed by a page under `src/app/`
- **THEN** a `*.stories.tsx` neighbour file exists in the component's directory
