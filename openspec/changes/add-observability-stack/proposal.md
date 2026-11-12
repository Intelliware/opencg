## Why

openCG promises that every stage is observable, but today the telemetry stops at the door. Spans go to a compose-local OpenTelemetry Collector that only prints them to its log, so nobody can search or chart them. Only the pipeline serves `/metrics`, and nothing scrapes it. The MCP server emits no traces or metrics at all, so a tool call and the pipeline work it triggers land in unrelated traces. Ingestion counts extraction tokens in a process nobody can scrape. Every model call is labelled `provider="ollama"`, whether it ran on the local Ollama container or on Ollama Cloud. There is no cost estimate, and none of the Grafana dashboards the v0 vision (`add-foundation`, observability capability) describes exist.

This change delivers that observability capability for the stages that exist today. It adds Prometheus, Tempo and Grafana as an opt-in compose overlay and closes the instrumentation gaps that would leave those backends half empty. Every model call reports token usage and an estimated cost, under a provider label of its own.

## What Changes

- **New opt-in compose overlay** `infra/compose/docker-compose.observability.yml` adding Prometheus, Tempo 3 and Grafana (pinned tags), plus `make up-obs` / `make down` support. The default `dev` stack, `make smoke` and the CI `stack` job keep their current footprint. The README quickstart, the README stack table and `docs/OPERATIONS.md` all say plainly that the backends are opt-in, how to turn them on and off, what they add, and what they cost in RAM and disk.
- **Collector wiring**: the overlay merges a second collector config that sends traces to Tempo. The base config keeps the `debug` exporter that the existing smoke relies on.
- **End-to-end traces**: the MCP server gains OpenTelemetry tracing (root span `mcp.<tool>`) and propagates W3C `traceparent` to the pipeline. The pipeline continues incoming traces. Every span carries `correlation_id`. Each model-provider call gets its own child span.
- **A provider label per model endpoint**: the `provider` field of each `providers.<role>` block becomes the label on every token, cost, error and span record. The checked-in default chat endpoint becomes `provider: ollama-cloud`, so local Ollama and Ollama Cloud are counted and priced apart. Hard-coded `provider="ollama"` strings in the pipeline go away. Older configs that say `provider: ollama` with an `ollama.com` base URL resolve to `ollama-cloud`, with a one-time log line.
- **Metrics on every service**: the MCP server and the ingestion service gain `/metrics`. Ingestion uses Prometheus multiprocess mode so CLI-driven runs (`make ingest-git`, the smoke) are counted by the long-lived server. The defined but unused series (`opencg_stage_latency_seconds` for every stage, `opencg_provider_errors_total`, error outcomes on `opencg_requests_total`) are wired up. New series cover ingestion runs per connector and audit writes.
- **Token accounting gap closed**: embedding calls made during ingestion are now counted (`stage="ingest_embed"`).
- **Token usage and cost on everything**: a `pricing` table in `opencg.yaml` keyed by provider, model and direction. The default table prices every model in the default configuration: local Ollama at zero, and Ollama Cloud at its published per-token rate (Ollama Cloud moved to per-token billing on 2026-08-31), each row recording its source and date. A new `opencg_cost_usd_total{provider,model,tenant}` counter is emitted alongside tokens. A model with no price is still counted, through `opencg_cost_unpriced_tokens_total`, and shown as "unpriced" rather than $0.
- **Usage envelope**: `/retrieve` responses (and so MCP results) gain `by_provider` and `estimated_cost_usd`. This is additive; existing fields keep their names.
- **Cost in the audit trail and the admin UI**: the retrieval audit row gains nullable `estimated_cost_usd` and `usage_by_provider` columns (a new init SQL file; the table stays append-only). Every admin UI view that shows token usage (the queries list, the audit detail page and the vector search result) also shows the estimated cost and a per-provider breakdown, "unpriced" when no price applies, and "—" for rows written before this change.
- **Dashboards as code**: six Grafana dashboards under `infra/grafana/dashboards/` (request volume and latency, per-stage latency, token spend and cost, ingestion health, audit volume, provider health). They are provisioned into an "openCG" folder against fixed datasource UIDs and checked by a static lint in `make ci-static`. Grafana requires a login; anonymous access is off.
- **Verification**: the default smoke also checks every service's `/metrics` for the required metric families. A new `make smoke-obs` applies the overlay and asserts that Prometheus targets are up, that token and cost series moved, that Tempo returns one connected trace for an MCP call, and that Grafana lists the shipped dashboards.
- **CI**: a new `observability` job runs `make smoke-obs` on every pull request to `main` and nightly. It is added to the `main` ruleset as a required check next to `static`, `stack` and `dependency-review`.
- **Docs**: `docs/OPERATIONS.md` gets an Observability runbook (enabling and disabling the overlay, ports, login, retention, RAM, the pricing table and how to update it, troubleshooting). The README quickstart, stack table and "Not in v0" list are updated. AGENTS.md, CLAUDE.md and `.cursor/rules/opencg.mdc` record the new required check and the new infra folders.

Not in this change: Loki and structured logs carrying `trace_id` (a follow-up change, `add-log-aggregation`, will be proposed once this one merges), Alertmanager and alert rules, admin-UI (Next.js) instrumentation, Tempo's metrics-generator and service graphs, and multi-tenant dashboard access control.

## Capabilities

### New Capabilities

- `observability`: cross-service tracing, the Prometheus metric set, cost estimation, the opt-in observability backends, the shipped Grafana dashboards and the required CI check. The name and scope come from `add-foundation/specs/observability`, cut down to the stages that exist today.

### Modified Capabilities

- `retrieval-pipeline`: "Per-stage token accounting" now covers ingestion embedding calls and pairs every token increment with a cost increment.
- `model-providers`: "ProviderConfig block": `provider` is the label used for metrics and pricing. The default chat endpoint becomes `ollama-cloud`, and an `ollama.com` base URL resolves to it.
- `admin-ui`: a new requirement to show estimated cost beside every token count.
- `smoke-testing`: "Observable smoke path" adds `/metrics` assertions to the default smoke, fixes the stale `hive-mind-ingestion` service name in its scenario, and adds the observability smoke.

## Impact

- **Code**: `packages/shared-py` (`metrics.py`, `otel.py`, `config.py`, `types.py`, new `pricing.py`), `packages/shared` (TS wire types for the usage envelope and audit row), `services/mcp-server` (new OTel and `prom-client` dependencies, `/metrics`, propagation), `services/pipeline` (trace-context extraction, stage histograms, provider-error and audit counters, cost, configured provider labels, audit cost columns), `services/ingestion` (`/metrics`, multiprocess registry, embed token accounting, run counters), `services/admin-ui` (cost beside token counts, stories and tests).
- **Database**: new `infra/postgres/init/060_audit_cost.sql` adding two nullable columns to `opencg.audit_log`. Existing rows keep `NULL`. The immutability trigger is unchanged.
- **Infra**: new `infra/compose/docker-compose.observability.yml`, `infra/otel/otel-collector.tempo.yaml`, `infra/prometheus/prometheus.yml`, `infra/tempo/tempo.yaml`, `infra/grafana/provisioning/**`, `infra/grafana/dashboards/*.json`. The ingestion service gets a `tmpfs` mount for the multiprocess metrics directory.
- **CI and repository settings**: new `observability` job in `.github/workflows/ci.yml`; `.github/rulesets/main-branch-protection.json` gains the `observability` required check, and the live ruleset is updated through `gh api` once the job has run green on `main`.
- **Config**: new `observability.pricing` block in `opencg.yaml`; `providers.chat.provider` default becomes `ollama-cloud`. New `.env.example` keys `OPENCG__GRAFANA__HOST_PORT`, `OPENCG__GRAFANA__ADMIN_PASSWORD`, `OPENCG__PROMETHEUS__HOST_PORT`, `OPENCG__PROMETHEUS__RETENTION`, `OPENCG__TEMPO__HOST_PORT`.
- **Dependencies**: new npm packages `@opentelemetry/sdk-trace-node`, `@opentelemetry/exporter-trace-otlp-http`, `@opentelemetry/api` and `prom-client`. Three new container images: `prom/prometheus:v3.15.1`, `grafana/tempo:3.1.1`, `grafana/grafana:13.2.5`.
- **Resources**: the overlay adds roughly 400 to 700 MB of RAM when running. The default stack is unchanged. Each PR gains one more CI job (estimated 8 to 12 minutes, running in parallel with `stack`).
- **Wire contract**: additive fields on `UsageEnvelope`. The `provider` label value changes from `ollama` to `ollama-cloud` for Ollama Cloud chat calls; dashboards or queries that filter on `provider="ollama"` for chat need updating (called out in the CHANGELOG).
