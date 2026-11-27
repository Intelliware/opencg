## ADDED Requirements

### Requirement: Single-command bring-up via Docker Compose

The repo SHALL ship a Docker Compose stack that brings up all required services with a single command (`docker compose up`). The stack SHALL include PostgreSQL+AGE, Qdrant, Valkey, OPA, the OpenTelemetry stack (collector, Tempo, Loki, Prometheus, Grafana), and the opencg services (MCP server, pipeline, enrichment workers, ingestion, admin UI).

#### Scenario: Fresh clone bring-up

- **WHEN** a developer clones the repo and runs `docker compose up`
- **THEN** all services start and report healthy within five minutes on a standard developer laptop
- **AND** the MCP server responds to `tools/list` after start

### Requirement: Dev vs. local-prod compose profiles

The compose stack SHALL expose two profiles: `dev` (mounts source, hot-reloads, exposes all admin ports, uses Anthropic if configured else Ollama) and `local-prod` (built images, restricted ports, persistent volumes).

#### Scenario: Profile selection

- **WHEN** the operator runs `docker compose --profile local-prod up -d`
- **THEN** the stack starts in the production-like configuration with persistent volumes mounted

### Requirement: Configuration model

A single `opencg.yaml` file SHALL configure the deployment: tenant slug, model providers per capability, connector configs, freshness thresholds, audit retention, telemetry endpoints, and entitlement defaults. Environment variables override file values.

#### Scenario: Override via env

- **WHEN** `OPENCG__EMBEDDINGS__PROVIDER=anthropic` is set
- **THEN** the embedding provider in effect at runtime is the Anthropic adapter, regardless of the file value

### Requirement: Health and readiness

Every service SHALL expose `/healthz` (liveness) and `/readyz` (readiness, including provider probes and storage probes). The compose stack SHALL gate dependents on `readyz`.

#### Scenario: Pipeline waits for storage

- **WHEN** Postgres is not yet ready
- **THEN** the pipeline service's `readyz` reports `not_ready` and the MCP server's `readyz` does as well

### Requirement: Persistent volumes for stateful services

The `local-prod` profile SHALL use named volumes for Postgres, Qdrant, Valkey, audit log storage, and Grafana to survive container restarts.

#### Scenario: Restart preserves data

- **WHEN** the stack is brought down with `docker compose down` and back up
- **THEN** previously ingested entities, audit records, and dashboards are still present
