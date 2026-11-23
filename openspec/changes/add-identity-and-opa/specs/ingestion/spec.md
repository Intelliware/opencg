## MODIFIED Requirements

### Requirement: Ingestion HTTP surface

The ingestion service SHALL expose the following HTTP endpoints on port `8100`:

- `GET /healthz` - liveness, returns `{"status":"ok"}`.
- `GET /readyz` - readiness; returns `200` once the underlying storage (Postgres + Qdrant + Ollama embeddings) is reachable.
- `GET /connectors` - returns a JSON array of `{name, supported, reason?}` entries. `git` MUST have `supported = true`. `confluence`, `custom-api`, and `web` MUST have `supported = false` with a `reason` naming the change that will implement them.
- `POST /run/git` - body `{"repo_url": <string>, "classification"?: <string>}`. MUST return `{run_id, status}` immediately and execute the git ingest in a background task using the same `pipeline_runner.run` code path as the CLI.
- `GET /runs/recent` - returns the most recent 100 runs as `[{run_id, connector, repo, started_at, finished_at, status, parents, chunks, error, classification, requested_by}]`, in-memory.

Run history MAY be in-memory only. Durability across container restarts is deferred to a follow-up change.

`classification` MUST default to `internal` and MUST match `public`, `internal` or `confidential:<domain>` where `<domain>` is lowercase letters, digits and hyphens; any other value MUST be rejected with `400`. Every parent and chunk entity created by the run MUST carry that classification in the catalogue and in the vector payload. The CLI MUST accept the same value through a `--classification` option.

In `oidc` mode, every endpoint except `/healthz` and `/readyz` MUST require a valid access token, `GET /connectors` and `GET /runs/recent` MUST be authorized as `ingestion.read`, and `POST /run/git` MUST be authorized as `ingestion.run` through the shared OPA client, with denials recorded in `opencg.access_audit_log`. `requested_by` MUST be the authenticated principal (the stub principal in `none` mode).

#### Scenario: Health endpoints

- **WHEN** the ingestion service is up
- **THEN** `GET /healthz` returns `200` with `{"status":"ok"}`
- **AND** `GET /readyz` returns `200` only when the storage backends are reachable

#### Scenario: Connectors enumeration

- **WHEN** a client calls `GET /connectors`
- **THEN** the response contains `git` with `supported = true`
- **AND** the response contains `confluence`, `custom-api`, and `web` with `supported = false` and a `reason` field

#### Scenario: Run lifecycle observable via /runs/recent

- **WHEN** a `POST /run/git` triggers a background run that eventually succeeds
- **THEN** `GET /runs/recent` shows the run progressing through `queued → running → succeeded`
- **AND** the final entry carries the populated `parents` and `chunks` counts

#### Scenario: Run failure surfaces error

- **WHEN** a `POST /run/git` triggers a background run that fails (e.g. unreachable repo)
- **THEN** the `/runs/recent` entry for that run reaches `status = failed`
- **AND** the entry carries a non-empty `error` string

#### Scenario: Classified run

- **WHEN** a client with `ingestion.run` permission posts `{"repo_url": "<fixture>", "classification": "confidential:legal"}`
- **THEN** every entity created by the run has `classification = "confidential:legal"` in the catalogue and in its Qdrant payload

#### Scenario: Invalid classification is rejected

- **WHEN** a client posts `{"repo_url": "<fixture>", "classification": "Top Secret"}`
- **THEN** the response is `400` and no run is queued

#### Scenario: Direct call without permission is refused

- **WHEN** in `oidc` mode a reader-only principal calls `POST /run/git` on port 8100 directly
- **THEN** the response is `403`, no run is queued, and an `access_audit_log` row records the denial
