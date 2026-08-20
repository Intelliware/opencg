## MODIFIED Requirements

### Requirement: Content management

The admin UI SHALL expose an entity browser at `/entities` and an entity detail page at `/entities/[id]`. The browser MUST support filtering by `source`, `classification`, and `freshness_state`, and MUST paginate with `limit` and `offset`. The detail page MUST show entity title, `source`, `source_uri`, `classification`, `freshness_state`, `last_verified_at`, `content_hash`, metadata JSON, lineage (parent entity if present + listing of chunks if this is a parent), the body text (first 50 KB with a "show full" toggle), and the audit appearances of this entity in the last N retrievals.

The detail page MUST expose a "Tombstone" action that posts `DELETE /entities/{id}` to the pipeline. Tombstoned entities MUST render with a visible banner indicating their state and the tombstone timestamp.

The browser's default ordering by `updated_at` now means **most recently changed** rather than most recently ingested. Ingestion no longer rewrites unchanged rows, so `updated_at` advances only when a file's content actually changes. Previously every ingest bumped it across the entire corpus, making the ordering arbitrary within a run and the displayed value a record of the last write rather than the last change.

#### Scenario: Browse entities by source

- **WHEN** an operator filters the entity browser by `source=git, classification=internal`
- **THEN** the response calls `GET /entities?source=git&classification=internal&limit=50&offset=0`
- **AND** the list renders the returned rows with `title`, `source_uri`, `classification`, `freshness_state`, and `updated_at`

#### Scenario: Inspect entity detail

- **WHEN** an operator opens `/entities/{id}`
- **THEN** the page shows the required fields and the lineage block
- **AND** the body section is collapsed to the first 50 KB with a "Show full body" toggle that fetches the rest

#### Scenario: Tombstone an entity

- **WHEN** an operator confirms the tombstone dialog for `entity_id = E1`
- **THEN** the page issues `DELETE /entities/E1` to the pipeline
- **AND** on success the page shows a "Tombstoned at …" banner
- **AND** subsequent calls to `GET /entities/E1` return the entity with a non-null `tombstoned_at`

#### Scenario: Unchanged entities do not rise to the top after a re-ingest

- **WHEN** a repository is re-ingested and only one file changed
- **THEN** that file's entity sorts above entities whose content did not change
- **AND** the unchanged entities retain their previous `updated_at` values

### Requirement: Content ingestion control

The admin UI SHALL expose `/ingestion`. The page MUST list configured connectors with `name`, `supported`, `last_run_at`, `last_run_status`, `last_run_error` if any, and recent runs (last 20) with `started_at`, `finished_at`, `status`, `parents`, `chunks`, `skipped`, and `error`. The page MUST include a "Run now" form for the git connector accepting a `repo_url` field, which POSTs `/ingestion/git/run` to the pipeline.

The `skipped` count reports documents the ingestion completion gate declined to reprocess. It is an operational safety surface, not decoration: a gate that skips more than it should produces a run that otherwise looks like a fast success, and the count is the only place that becomes visible.

`IngestionRunRow` renders the run grid cells and MUST carry the new column, with its `*.stories.tsx` neighbour updated accordingly per the Storybook coverage requirement.

#### Scenario: Trigger a git ingest from the UI

- **WHEN** an operator submits `repo_url = https://github.com/<owner>/<repo>` in the Run-now form
- **THEN** the UI calls `POST /ingestion/git/run` and renders a row in the recent-runs list for the new run with `status = queued` or `status = running`
- **AND** the row updates to `succeeded` (with `parents`, `chunks`, and `skipped` counts) or `failed` (with `error`) as the run completes

#### Scenario: Connector listing surfaces deferred connectors

- **WHEN** the page renders the connector list
- **THEN** the git connector appears with `supported = true`
- **AND** the deferred connectors (`confluence`, `custom-api`, `web`) appear with `supported = false` and a `Reason` tooltip naming the follow-up change

#### Scenario: A fully skipped run is legible

- **WHEN** a re-ingest of an unchanged repository completes having skipped every document
- **THEN** the run row shows a non-zero `skipped` count and a zero `chunks` count
- **AND** the run is not presented as having ingested nothing
