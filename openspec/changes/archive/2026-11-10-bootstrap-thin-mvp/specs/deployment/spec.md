## MODIFIED Requirements

### Requirement: Single-command bring-up via Docker Compose

The repo SHALL ship a Docker Compose stack that brings up all required services with a single command. In v0 the stack MUST include PostgreSQL+AGE, Qdrant, Valkey, an Ollama embeddings service, the MCP server, the pipeline, the ingestion container, and the admin UI. OPA, the OpenTelemetry collector, and the Tempo/Loki/Prometheus/Grafana telemetry stack are deferred.

#### Scenario: Fresh clone bring-up

- **WHEN** a developer clones the repo, copies `.env.example` to `.env`, and runs `docker compose -f infra/compose/docker-compose.yml --profile dev up`
- **THEN** Postgres, Qdrant, Valkey, Ollama, the pipeline, the MCP server, the ingestion container, and the admin UI all start
- **AND** the MCP server's `/readyz` returns `200` after the pipeline and Ollama become healthy
- **AND** the configured embedding model is pulled and usable by the embeddings client

### Requirement: Dev vs. local-prod compose profiles

The compose stack SHALL expose only the `dev` profile in v0. The `local-prod` profile, restricted ports, and the stub-identity startup guard MUST be added by a follow-up change before any non-development deployment.

#### Scenario: Only the dev profile is shipped in v0

- **WHEN** the operator inspects `docker compose --profile local-prod config`
- **THEN** no services are matched

### Requirement: Configuration model

A single `opencg.yaml` file SHALL configure the deployment. Environment variables MUST override file values using the convention `OPENCG__<SECTION>__<KEY>` with double underscores between nesting levels.

In v0 the file MUST cover identity stub, storage URLs (Postgres, Qdrant, Valkey), Ollama embeddings (`base_url`, `embedding_model`, optional `api_key`), retrieval defaults (`default_top_k`, `default_token_budget`, `tokens_per_char`), audit retention placeholder, and telemetry endpoint placeholder. Sections for deferred capabilities are introduced by their respective follow-up changes.

#### Scenario: Override Ollama base URL via env

- **WHEN** `OPENCG__OLLAMA__BASE_URL` is set to `http://other-host:11434`
- **THEN** the pipeline and ingestion services target that URL for embeddings

### Requirement: Health and readiness

Every service SHALL expose `/healthz` (liveness) and `/readyz` (readiness). The compose stack MUST gate dependent services on `service_healthy` for upstream services.

#### Scenario: Pipeline waits for storage

- **WHEN** Postgres is not yet ready
- **THEN** the pipeline service's `/readyz` reports `not_ready`

### Requirement: Persistent volumes for stateful services

The compose stack SHALL use named volumes for every stateful service it ships. In v0 this MUST include Postgres, Qdrant, Valkey, and Ollama. Volumes for audit log archival and Grafana are deferred until the relevant follow-up changes ship those services.

#### Scenario: Restart preserves data

- **WHEN** the stack is brought down with `docker compose down` (without `-v`) and brought back up
- **THEN** previously ingested entities, audit records, and the downloaded Ollama model are still present

## ADDED Requirements

### Requirement: Ollama compose service as the embeddings backend

The compose stack SHALL include an `ollama` service running the official `ollama/ollama` image, with a named volume for model storage. The service MUST expose a healthcheck that fails until the configured embedding model is usable. The `pipeline` and `ingestion` services MUST declare a `depends_on` clause that gates them on `ollama: { condition: service_healthy }`.

#### Scenario: Ollama service is part of the dev profile

- **WHEN** the operator runs `docker compose --profile dev config`
- **THEN** the `ollama` service appears in the output
- **AND** the `pipeline` and `ingestion` services declare a `service_healthy` dependency on `ollama`

#### Scenario: Embedding model is available on first start

- **WHEN** the stack starts for the first time on a host where the configured embedding model has never been pulled
- **THEN** the Ollama service pulls the configured model before reporting itself healthy
- **AND** the subsequent first embedding call from pipeline or ingestion succeeds
