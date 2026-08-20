---
id: observability
title: Observability
capabilities: observability
status: partial
services: pipeline, ingestion, otel-collector
tagline: Traces and metrics, with token accounting treated as mandatory.
---

## What it is

OpenTelemetry traces plus Prometheus metrics, exported to a collector running in
the compose stack. Every pipeline stage opens a span; every model call reports
its tokens.

## Why it exists

Two questions need answering continuously. **Where did the latency go** — which
matters because retrieval fans out to several backends and any one of them can be
the slow one. And **what did this cost** — which matters because tokens are the
unit of spend, and per-stage attribution is the only way to know which stage to
optimise.

The project rules make token reporting non-negotiable: a model call that does not
emit a token count is treated as a bug, not an omission.

## Flow

### 1. Bootstrap tracing per service
Each service calls `setup_otel` with its name, which wires an OTLP HTTP exporter
pointed at `http://otel-collector:4318/v1/traces`. Setting the endpoint to `none`
or `off` disables export cleanly, so tests and offline runs do not need a
collector.
file: packages/shared-py/src/opencg_shared/otel.py

### 2. Span the request and each stage
`/retrieve` opens `pipeline.retrieve` with correlation id, tenant, principal, and
tool, then child spans per stage. `pipeline.hybrid_retrieval` carries dense,
lexical, and fused counts plus the embedding model; `pipeline.assemble` carries
candidates in, kept, and budget.
file: services/pipeline/src/opencg_pipeline/app.py

### 3. Count tokens on every model call
`record_stage_tokens` increments
`opencg_tokens_total{stage,model,provider,tenant,direction}` and the same numbers
are set as span attributes. Both the trace and the time series can answer the
cost question independently.
file: packages/shared-py/src/opencg_shared/metrics.py

### 4. Count extraction outcomes
Graph extraction emits `opencg_extractor_edges_total{relation,state}` for edges
it produced and `opencg_extractor_errors_total{reason}` for timeouts, provider
failures, and parse failures — which is what makes best-effort extraction
observable rather than silent.
file: services/pipeline/src/opencg_pipeline/graph/extract.py

### 5. Expose a scrape endpoint
The pipeline serves Prometheus text at `GET /metrics`, mounted from the shared
metrics app so every service exposes the same registry shape.
file: packages/shared-py/src/opencg_shared/metrics.py

### 6. Return usage in the response too
Beyond telemetry, `/retrieve` returns a `UsageEnvelope` with total tokens,
latency, and a per-stage breakdown, so a caller sees its own cost without needing
access to the metrics backend.
file: packages/shared-py/src/opencg_shared/types.py

## Facts
- Collector: **otel-collector-contrib 0.123.0**, OTLP HTTP on 4318, health on 13133
- Service names: `opencg-pipeline`, `opencg-ingestion`
- Key metrics: `opencg_tokens_total`, `opencg_requests_total`, `opencg_stage_latency_seconds`, `opencg_extractor_edges_total`, `opencg_extractor_errors_total`, `opencg_provider_errors_total`
- Token labels: `stage`, `model`, `provider`, `tenant`, `direction`
- Set the OTLP endpoint to `none` or `off` to disable export

## Gaps
- **No Grafana, Tempo, Loki, or Prometheus server.** The collector receives traces but nothing stores or visualises them; the full stack is specced in `add-foundation` and deferred.
- **`opencg_stage_latency_seconds` is only recorded for graph extraction.** Retrieve stages return latency in the response body but never populate the histogram, so stage latency is not queryable over time.
- **`opencg_provider_errors_total` is defined but never incremented** on the retrieve path.
- **No structured log aggregation** — logs go to stdout and stay there.
- **No alerting or SLOs.**
