## ADDED Requirements

### Requirement: OpenTelemetry tracing across stages

Every service SHALL emit OpenTelemetry traces. A single request SHALL produce a root span at the MCP server and one child span per pipeline stage (and per model call within a stage), all linked by the request correlation ID and a W3C trace context.

#### Scenario: Trace shape

- **WHEN** an MCP `retrieve_for_context` call is made
- **THEN** the resulting trace contains spans for `mcp.retrieve_for_context`, `pipeline.identity`, `pipeline.intent`, `pipeline.hybrid_retrieval`, `pipeline.catalog_graph`, `pipeline.rerank_compress`, `pipeline.entitle_audit`, `pipeline.return`, plus one model-call child span per provider invocation
- **AND** all spans share the same `trace_id` and `correlation_id` attribute

### Requirement: Prometheus metrics

Each service SHALL expose `/metrics` in Prometheus format. The standard set SHALL include `opencg_requests_total{tool,outcome}`, `opencg_stage_latency_seconds_bucket{stage}`, `opencg_tokens_total{stage,model,provider,tenant,direction}`, `opencg_provider_errors_total{provider,error_code}`, and ingestion counters per connector.

#### Scenario: Metrics endpoint returns required series

- **WHEN** Prometheus scrapes any service `/metrics`
- **THEN** the required metric families are present

### Requirement: Per-stage token accounting

Every stage that invokes a model provider SHALL record input and output token counts and emit them as both span attributes and Prometheus counter increments. Aggregate per-request token usage SHALL be exposed in the response envelope under `usage`.

#### Scenario: Usage in response envelope

- **WHEN** an MCP tool call completes
- **THEN** the response includes `usage: { input_tokens, output_tokens, by_stage: [...], by_provider: [...] }`

### Requirement: Cost estimation

The system SHALL maintain a cost-per-1k-tokens table per `(provider, model, direction)` and SHALL compute and emit `opencg_cost_usd_total{provider,model,tenant}` alongside token counts.

#### Scenario: Cost computed for Anthropic call

- **WHEN** an Anthropic provider call records `tokens_in = 500`, `tokens_out = 100`
- **THEN** `opencg_cost_usd_total` increases by the configured rate for that model and direction

### Requirement: Grafana dashboards shipped

The repo SHALL ship a `infra/grafana/dashboards/` directory containing dashboards for: request volume + latency, per-stage latency, token spend (by tenant/provider/model), ingestion health, audit volume, and provider health.

#### Scenario: Dashboards present

- **WHEN** the deployment stack starts
- **THEN** Grafana is provisioned with the shipped dashboards visible under a "openCG" folder
