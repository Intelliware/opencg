## ADDED Requirements

### Requirement: OpenTelemetry tracing in every service

The MCP server, the pipeline and the ingestion service SHALL each export OpenTelemetry traces over OTLP/HTTP to the compose-local collector, with resource attributes `service.name` (`opencg-mcp-server`, `opencg-pipeline`, `opencg-ingestion`) and `service.namespace` (from `telemetry.service_namespace`). Setting `OTEL_EXPORTER_OTLP_ENDPOINT` to `none`, `off`, `disabled` or empty MUST disable export without errors.

#### Scenario: MCP server spans reach the collector

- **WHEN** a client calls any MCP tool while the collector is running
- **THEN** the collector receives a span from a resource with `service.name = opencg-mcp-server`

#### Scenario: Export disabled

- **WHEN** `OTEL_EXPORTER_OTLP_ENDPOINT` is set to `none`, `off`, `disabled` or an empty value
- **THEN** every service starts and serves requests without an exporter
- **AND** no service retries or logs connection errors for a missing collector

### Requirement: One connected trace per MCP tool call

The MCP server MUST open a root span named `mcp.<tool>` (for example `mcp.retrieve_for_context`) for every tool call and MUST propagate the W3C `traceparent` header on every request it makes to the pipeline. The pipeline MUST continue an incoming trace context rather than start a new trace. Spans for stages that do not exist yet are out of scope; each later change that adds a stage MUST add its span under the same root.

#### Scenario: One trace per MCP retrieve call

- **WHEN** a client calls the MCP tool `retrieve_for_context` and the call succeeds
- **THEN** the collector receives spans `mcp.retrieve_for_context`, `pipeline.retrieve`, `pipeline.identity`, `pipeline.hybrid_retrieval`, `pipeline.assemble` and at least one `model.embed`
- **AND** all of those spans share one `trace_id`

#### Scenario: Direct pipeline call without a trace context

- **WHEN** a caller posts to the pipeline's `/retrieve` without a `traceparent` header
- **THEN** the pipeline starts a new trace whose root span is `pipeline.retrieve`

### Requirement: Correlation ID on every span

Every span created while serving an MCP tool call, a pipeline request or an ingestion run MUST carry a `correlation_id` attribute. For tool calls and pipeline requests it is the request's correlation ID. For ingestion runs it is the run ID.

#### Scenario: All spans of a retrieval share the correlation ID

- **WHEN** a `/retrieve` call with `correlation_id = "c-1"` completes
- **THEN** every span in its trace has the attribute `correlation_id = "c-1"`

### Requirement: Model-call child spans

Every call to a model provider SHALL get its own child span named `model.<operation>` (`model.embed`, `model.chat`) under the span of the stage that made it. The span MUST carry `provider`, `model`, `tokens_in`, `tokens_out`, `latency_ms` and `cost_usd`.

#### Scenario: Embedding call span

- **WHEN** the hybrid retrieval stage embeds a query through the embeddings provider
- **THEN** a `model.embed` span is a child of `pipeline.hybrid_retrieval`
- **AND** it carries `provider`, `model`, `tokens_in`, `tokens_out`, `latency_ms` and `cost_usd`

### Requirement: Prometheus metrics endpoint on every service

The MCP server, the pipeline and the ingestion service SHALL each serve `GET /metrics` in the Prometheus text format, without authentication, on the same port as their health endpoints. Metric labels MUST NOT contain query text, principal names, entity IDs, correlation IDs or any other unbounded value.

#### Scenario: Endpoint reachable without credentials

- **WHEN** `OPENCG__MCP__HTTP_TOKEN` is set and a scraper requests the MCP server's `/metrics` without a token
- **THEN** the response is HTTP 200 in the Prometheus text format
- **AND** `/mcp` still rejects requests without the token

### Requirement: Standard metric families

The pipeline SHALL expose `opencg_requests_total{tool,outcome}` (`outcome` is `ok`, `error` or `rejected`), `opencg_stage_latency_seconds{stage}` (histogram), `opencg_tokens_total{stage,model,provider,tenant,direction}`, `opencg_cost_usd_total{provider,model,tenant}`, `opencg_cost_unpriced_tokens_total{provider,model}`, `opencg_provider_errors_total{provider,error_code}` and `opencg_audit_writes_total{log,outcome}`.

#### Scenario: Pipeline families present

- **WHEN** a test scrapes the pipeline's `/metrics` after one `/retrieve` call
- **THEN** every family listed in this requirement is present

#### Scenario: Errors are counted

- **WHEN** a `/retrieve` call fails with an unhandled error
- **THEN** `opencg_requests_total{outcome="error"}` increases by one for that tool

#### Scenario: Provider failures are counted

- **WHEN** a model-provider call fails with an HTTP error or a timeout
- **THEN** `opencg_provider_errors_total{provider,error_code}` increases by one, where `error_code` is the HTTP status or `timeout`

#### Scenario: Every pipeline stage is timed

- **WHEN** a `/retrieve` call completes
- **THEN** `opencg_stage_latency_seconds_count` increases for `identity`, `hybrid_retrieval` and `assemble`

#### Scenario: Audit writes are counted

- **WHEN** a `/retrieve` call writes its audit row
- **THEN** `opencg_audit_writes_total{log="retrieval",outcome="ok"}` increases by one

### Requirement: Ingestion and MCP metric families

The ingestion service SHALL expose the token, cost, unpriced-token, provider-error and stage-latency families, plus `opencg_ingestion_runs_total{connector,status}`, `opencg_ingestion_documents_total{connector}`, `opencg_ingestion_chunks_total{connector}` and `opencg_ingestion_run_duration_seconds{connector}` (histogram). The MCP server SHALL expose `opencg_requests_total{tool,outcome}` and `opencg_stage_latency_seconds{stage="mcp"}`.

#### Scenario: Ingestion families present

- **WHEN** a test scrapes the ingestion service's `/metrics` after one successful git ingestion run
- **THEN** the ingestion run, document, chunk, duration and token families are present

#### Scenario: MCP families present

- **WHEN** a test scrapes the MCP server's `/metrics` after one tool call
- **THEN** `opencg_requests_total` and `opencg_stage_latency_seconds` with `stage="mcp"` are present

### Requirement: Ingestion metrics survive one-shot CLI runs

Ingestion runs started from the CLI inside the ingestion container (as `make ingest-git` and the smoke do) SHALL be counted in the ingestion service's `/metrics` just like runs started over HTTP. Counters MUST accumulate across processes and MUST NOT reset when a CLI process exits. They MAY reset when the ingestion container restarts. A family MAY be absent from the scrape until some process records a value for it.

#### Scenario: CLI run visible to the scraper

- **WHEN** an operator runs `make ingest-git REPO=<repo>` and the run succeeds
- **THEN** a later scrape of the ingestion service's `/metrics` shows `opencg_ingestion_runs_total{connector="git",status="succeeded"}` increased by one
- **AND** shows `opencg_tokens_total{stage="ingest_embed"}` increased by the run's embedding tokens

### Requirement: Configured price table

The system SHALL read a price table from `observability.pricing` in `opencg.yaml`. Each entry has `provider`, `model`, `input_usd_per_1k`, `output_usd_per_1k`, and a required `source` and `as_of`. The default table SHALL price local Ollama at zero and every Ollama Cloud model on Ollama's published price list at its per-token rate. Price changes MUST take effect on restart and MUST NOT rewrite past counters or audit rows.

#### Scenario: Local Ollama is free

- **WHEN** a query is embedded with the default compose-local Ollama model and the default price table
- **THEN** `opencg_tokens_total` increases
- **AND** `opencg_cost_usd_total` for that provider and model increases by zero
- **AND** `opencg_cost_unpriced_tokens_total` does not increase for that pair

#### Scenario: A published Ollama Cloud model is priced by default

- **WHEN** the chat endpoint is set to an Ollama Cloud model on the published price list (for example `gemma4`) and the text extractor calls it with the default price table
- **THEN** `opencg_cost_usd_total{provider="ollama-cloud",model="gemma4"}` increases by a value greater than zero
- **AND** `opencg_cost_unpriced_tokens_total` does not increase for that pair

#### Scenario: A model missing from the price list stays visible

- **WHEN** the extractor calls `gemma3:4b`, which is not on Ollama's price list as of 2026-11-12
- **THEN** its tokens are counted in `opencg_cost_unpriced_tokens_total{provider="ollama-cloud",model="gemma3:4b"}`

#### Scenario: Entry without provenance is rejected

- **WHEN** a price table entry has no `source` or no `as_of`
- **THEN** configuration loading fails with an error naming the entry

### Requirement: Cost computed wherever tokens are counted

Wherever tokens are counted, the system SHALL compute cost as `tokens_in / 1000 × input_usd_per_1k + tokens_out / 1000 × output_usd_per_1k` and add it to `opencg_cost_usd_total{provider,model,tenant}`. For a pair with no price entry, the reported cost MUST be `null` (never zero), the tokens MUST be added to `opencg_cost_unpriced_tokens_total{provider,model}`, and the service MUST log one warning per pair per process.

#### Scenario: Cost computed for a priced call

- **WHEN** the price table has `{provider: anthropic, model: claude-haiku, input_usd_per_1k: 0.001, output_usd_per_1k: 0.005}` and a call records 500 input tokens and 100 output tokens
- **THEN** `opencg_cost_usd_total{provider="anthropic",model="claude-haiku"}` increases by 0.001

#### Scenario: Unpriced model is visible

- **WHEN** a call is made to a `(provider, model)` pair with no price entry
- **THEN** the cost counter is not increased
- **AND** `opencg_cost_unpriced_tokens_total{provider,model}` increases by the call's tokens
- **AND** a warning naming the pair is logged once by that process

### Requirement: Usage envelope reports providers and cost

The `usage` object on `/retrieve` and `/search/vector` responses, and on MCP tool results built from them, SHALL keep its existing fields and add `by_provider` (one `{provider, model, tokens_in, tokens_out, cost_usd}` per pair used), `estimated_cost_usd` (sum of the non-null `cost_usd` values) and `cost_complete` (false if any `cost_usd` is `null`). Each `by_stage` entry SHALL carry `provider` and `cost_usd`.

#### Scenario: Envelope sums match

- **WHEN** a `/retrieve` call completes
- **THEN** `usage.by_provider` has one entry per provider and model used
- **AND** the sum of `tokens_in` across `by_provider` equals `usage.total_tokens_in`
- **AND** `usage.estimated_cost_usd` equals the sum of the non-null `cost_usd` values across `by_provider`

#### Scenario: Unpriced provider is flagged, not zeroed

- **WHEN** a `/retrieve` call uses a `(provider, model)` pair with no price entry
- **THEN** that pair's `by_provider` entry has `cost_usd = null`
- **AND** `usage.cost_complete` is false

#### Scenario: Existing fields unchanged

- **WHEN** an existing client reads `total_tokens_in`, `total_tokens_out`, `total_latency_ms` or `by_stage`
- **THEN** those fields keep their current names, types and meaning

### Requirement: Opt-in observability overlay

The repository SHALL ship `infra/compose/docker-compose.observability.yml`, which adds Prometheus, Tempo and Grafana at pinned image tags and routes collector traces to Tempo. The default `dev` stack MUST NOT start these services and MUST keep the collector's `debug` exporter. `make up-obs` SHALL start the dev stack with the overlay, and `make down` SHALL also remove the overlay's containers.

#### Scenario: Default stack unchanged

- **WHEN** an operator runs `make up-d`
- **THEN** no Prometheus, Tempo or Grafana container is started
- **AND** the collector accepts OTLP/HTTP and logs spans as it does today

#### Scenario: Traces reach Tempo

- **WHEN** the overlay is applied and an MCP `retrieve_for_context` call completes
- **THEN** a Tempo search for that call's `correlation_id` returns exactly one trace containing `mcp.retrieve_for_context` and `pipeline.hybrid_retrieval`

#### Scenario: Teardown removes overlay containers

- **WHEN** an operator runs `make down` after `make up-obs`
- **THEN** no Prometheus, Tempo or Grafana container remains

### Requirement: Backend ports, scraping and retention

Overlay ports MUST follow `${OPENCG__BIND_ADDRESS:-127.0.0.1}:${OPENCG__<SERVICE>__HOST_PORT:-<default>}`, with defaults Grafana 3030 (3001 is taken by the e2e overlay), Prometheus 9090 and Tempo 3200. Prometheus MUST scrape the pipeline, ingestion service, MCP server and collector. Prometheus retention MUST default to 7 days (`OPENCG__PROMETHEUS__RETENTION`), Tempo's to 48 hours. Each backend MUST use a named volume.

#### Scenario: Prometheus targets up

- **WHEN** an operator runs `make up-obs` and the stack is healthy
- **THEN** the Prometheus targets API reports the pipeline, ingestion, MCP server and collector targets as `up`

#### Scenario: Port override

- **WHEN** `.env` sets `OPENCG__GRAFANA__HOST_PORT=3333`
- **THEN** Grafana is published on `127.0.0.1:3333` and nothing listens on host port 3030 for it

#### Scenario: Volumes removed with the stack

- **WHEN** an operator runs `make down-v`
- **THEN** the Prometheus, Tempo and Grafana named volumes are deleted

### Requirement: Grafana provisioning as code

The repository SHALL ship Grafana provisioning under `infra/grafana/provisioning/` and dashboard JSON under `infra/grafana/dashboards/`. Datasources MUST have fixed UIDs (`opencg-prometheus`, `opencg-tempo`), and dashboards MUST reference datasources only by those UIDs. Dashboards MUST be provisioned into a folder named "openCG" with UI edits not persisted.

#### Scenario: Dashboards provisioned on start

- **WHEN** the overlay stack starts
- **THEN** the Grafana search API lists every dashboard in `infra/grafana/dashboards/` inside the "openCG" folder

#### Scenario: Static dashboard lint

- **WHEN** `make ci-static` runs
- **THEN** it fails if any dashboard file is invalid JSON, lacks a stable `uid`, references a datasource UID other than `opencg-prometheus` or `opencg-tempo`, or queries an `opencg_*` metric that the shared metrics module does not define

### Requirement: Shipped dashboard set

The shipped dashboards SHALL cover request volume and latency, per-stage latency, token spend and estimated cost by tenant, provider and model, ingestion health, audit volume, and provider health. Every PromQL expression in them MUST reference only the standard metric families or the collector's own metrics.

#### Scenario: All six areas covered

- **WHEN** a reviewer lists `infra/grafana/dashboards/`
- **THEN** there is a dashboard for each of the six areas named in this requirement
- **AND** after `make smoke-obs` every panel on the request, stage, token and ingestion dashboards shows data

### Requirement: Provider label from configuration

Every token, cost, provider-error and span record of a model call SHALL take its `provider` value from the configured endpoint that served the call. No service MAY hard-code a provider label. Distinct model endpoints (for example local Ollama and Ollama Cloud) MUST report distinct provider labels.

#### Scenario: Local and Cloud Ollama counted apart

- **WHEN** the default stack embeds a query on the local Ollama container and the text extractor calls Ollama Cloud
- **THEN** `opencg_tokens_total` has series with `provider="ollama"` for the embedding model and `provider="ollama-cloud"` for the chat model

#### Scenario: Retrieval reports the configured provider

- **WHEN** `providers.embeddings.provider` is set to `my-embedder` and a `/retrieve` call completes
- **THEN** the `hybrid_retrieval` usage entry, its `model.embed` span and its `opencg_tokens_total` series all carry `provider="my-embedder"`

### Requirement: Cost recorded in the retrieval audit trail

Each retrieval audit row SHALL record `estimated_cost_usd` and `usage_by_provider` from the request's usage envelope. Both columns MUST be nullable so rows written before this change remain valid, and adding them MUST NOT weaken the audit log's append-only enforcement.

#### Scenario: Audit row carries cost

- **WHEN** a `/retrieve` call completes with the default price table
- **THEN** its audit row has `estimated_cost_usd` equal to the response's `usage.estimated_cost_usd`
- **AND** `usage_by_provider` equals the response's `usage.by_provider`

#### Scenario: Audit log stays append-only

- **WHEN** a client tries to `UPDATE` the `estimated_cost_usd` of an existing audit row
- **THEN** the database rejects the statement

### Requirement: Observability overlay documented as opt-in

The README quickstart, the README stack table, `docs/OPERATIONS.md`, `make help` and `.env.example` SHALL each state that Prometheus, Tempo and Grafana are opt-in and started with `make up-obs`. `docs/OPERATIONS.md` SHALL also describe what the overlay adds, how to stop it, what keeps working without it, its ports and login, retention, disk and RAM cost, the pricing table and how to refresh its rates, and troubleshooting for targets down and missing traces.

#### Scenario: A new user finds the overlay from the quickstart

- **WHEN** a reader follows the README quickstart
- **THEN** it includes an optional observability step naming `make up-obs`, the Grafana URL and the extra RAM it needs

#### Scenario: The runbook covers the overlay

- **WHEN** a reviewer reads the Observability section of `docs/OPERATIONS.md`
- **THEN** it covers starting and stopping the overlay, what works without it, ports, login, retention, RAM, the pricing table and troubleshooting

### Requirement: Grafana requires sign-in

Grafana in the overlay SHALL have anonymous access disabled. Its admin password SHALL come from `OPENCG__GRAFANA__ADMIN_PASSWORD`.

#### Scenario: Anonymous request refused

- **WHEN** a client requests a provisioned dashboard from Grafana's API without credentials
- **THEN** Grafana responds with HTTP 401

### Requirement: Observability check required on main

CI SHALL run `make smoke-obs` in a job named `observability` on every pull request to `main`, on every push to `main` and on a nightly schedule, with no path filter. The repository's `main` ruleset SHALL list `observability` as a required status check alongside `static`, `stack` and `dependency-review`.

#### Scenario: Every pull request runs the check

- **WHEN** a pull request to `main` changes only documentation
- **THEN** the `observability` job runs and reports a status

#### Scenario: Ruleset requires the check

- **WHEN** a reviewer reads `.github/rulesets/main-branch-protection.json`
- **THEN** `observability` is listed under `required_status_checks`
