## MODIFIED Requirements

### Requirement: OpenTelemetry tracing across stages

Every service SHALL emit OpenTelemetry traces using the W3C trace context. A single retrieval request MUST produce a root span at the MCP server and one child span per implemented pipeline stage and per model call, linked by the correlation ID.

In v0 the spans MUST be emitted, but the OTel collector + Tempo backend MAY be absent. The spans are exportable as soon as `OTEL_EXPORTER_OTLP_ENDPOINT` points at a live collector.

#### Scenario: Thin-MVP trace shape

- **WHEN** a `retrieve_for_context` call is made
- **THEN** the resulting trace contains spans named `mcp.retrieve_for_context`, `pipeline.retrieve`, `pipeline.identity`, `pipeline.hybrid_retrieval`, and `pipeline.assemble`, plus one child span per model call inside `pipeline.hybrid_retrieval`
- **AND** all spans share the same `trace_id` and `correlation_id` attribute

### Requirement: Prometheus metrics

Each service SHALL expose `/metrics` in Prometheus format. The standard set MUST include `opencg_requests_total{tool,outcome}`, `opencg_stage_latency_seconds_bucket{stage}`, `opencg_tokens_total{stage,model,provider,tenant,direction}`, and `opencg_provider_errors_total{provider,error_code}`.

In v0 only the pipeline service MUST expose the counters above. Ingestion counters are deferred to the follow-up change that adds the connector framework with metrics hooks. No Prometheus scraper is bundled in v0.

#### Scenario: Pipeline metrics endpoint returns required series

- **WHEN** any HTTP client scrapes `GET /metrics` on the pipeline service after a single successful retrieve
- **THEN** the response contains `opencg_requests_total`, `opencg_tokens_total`, and the stage-latency histogram

### Requirement: Per-stage token accounting

Every stage that invokes a model provider SHALL record input and output token counts on its OTel span AND increment the Prometheus token counter. Aggregate per-request token usage MUST be exposed in the response envelope under `usage`.

In v0 only the hybrid retrieval stage invokes a model. Its span and counter MUST carry the embeddings `model` and `provider`. Other stages MUST report zero token counts.

#### Scenario: Usage in response envelope

- **WHEN** an MCP tool call completes
- **THEN** the response includes `usage: { total_tokens_in, total_tokens_out, total_latency_ms, by_stage: [...] }`
- **AND** the `hybrid_retrieval` entry in `by_stage` carries the embeddings `model` and `provider`

### Requirement: Cost estimation

The system SHALL NOT emit a cost metric in v0. A follow-up change MUST introduce the cost-per-1k-tokens table and the `opencg_cost_usd_total` counter together.

#### Scenario: Cost metric is absent in v0

- **WHEN** Prometheus scrapes the pipeline `/metrics` in the thin MVP
- **THEN** the `opencg_cost_usd_total` metric series is not present

### Requirement: Grafana dashboards shipped

The system SHALL NOT ship Grafana or any dashboards in v0. A follow-up change MUST introduce them together with the Tempo/Loki/Prometheus/Grafana stack.

#### Scenario: Grafana is absent in v0

- **WHEN** the operator brings up the v0 compose stack
- **THEN** no Grafana service is present and no provisioning directory is created
