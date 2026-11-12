## Context

The `add-foundation` vision lists observability as one of its twelve capabilities: OTel traces across stages, Prometheus metrics, per-stage token accounting, cost estimation and shipped Grafana dashboards. The thin MVP delivered only part of it. Reading the code on `main` (as of 2026-11-12) shows this:

**What exists**

- `infra/otel/otel-collector.yaml`: an OTLP/HTTP receiver on 4318, a `batch` processor and a `debug` exporter only. The collector runs in the `dev` profile (`otel/opentelemetry-collector-contrib:0.123.0`).
- `packages/shared-py/opencg_shared/otel.py`: `setup_otel()` builds a tracer provider with an OTLP/HTTP span exporter. It reads `OTEL_EXPORTER_OTLP_ENDPOINT` and ignores `telemetry.otlp_endpoint` in `opencg.yaml`.
- `packages/shared-py/opencg_shared/metrics.py`: a private `CollectorRegistry` with `opencg_requests_total`, `opencg_stage_latency_seconds`, `opencg_tokens_total`, `opencg_provider_errors_total`, `opencg_extractor_edges_total` and `opencg_extractor_errors_total`, plus a `metrics_app` handler.
- Pipeline: `/metrics` is mounted. `/retrieve` emits `pipeline.retrieve` → `pipeline.identity`, `pipeline.hybrid_retrieval`, `pipeline.assemble`, and `/search/vector` emits `pipeline.vector_search`. Tokens are recorded for `hybrid_retrieval`, `vector_search` and `graph_extract_text`.
- Smoke (`tests/smoke/run.sh`): greps `docker compose logs otel-collector` for the extraction spans and token attributes. The smoke relies on the `debug` exporter.
- `docs/OPERATIONS.md` and the README say that Tempo and Grafana are a follow-up.

**Gaps found**

1. **The MCP server has no telemetry.** It has no OTel SDK, no `/metrics` and no `traceparent` on its `undici` calls. A tool call cannot be linked to the pipeline trace it causes.
2. **The pipeline does not continue incoming traces.** There is no FastAPI instrumentation and no propagator extraction, so every `/retrieve` starts a new trace.
3. **Only the root span has `correlation_id`.** The child stage spans do not.
4. **There are no model-call child spans.** Model attributes sit on the stage span.
5. **Ingestion has no `/metrics`.** Its token and extractor counters live in a process nobody scrapes. Worse, `make ingest-git` and the smoke run ingestion as a one-shot CLI process (`docker compose exec … python -m opencg_ingestion.cli`), so the counters vanish when the process exits.
6. **Ingestion embedding tokens are not counted at all** (`pipeline_runner.py` calls `embeddings.embed` and never calls `record_stage_tokens`).
7. **`opencg_stage_latency_seconds` is only observed for `graph_extract_text`.** No pipeline stage is timed in Prometheus.
8. **`opencg_provider_errors_total` is defined but never incremented.**
9. **`opencg_requests_total` only counts `outcome="ok"`.** Failures are invisible.
10. **There are no ingestion run counters per connector and no audit-write counter.** The vision's "ingestion health" and "audit volume" dashboards would have nothing to plot.
11. **There is no cost model**, and the `UsageEnvelope` has no `by_provider`.
12. **The baseline `smoke-testing` scenario still names `hive-mind-ingestion`**, though the script already checks `opencg-ingestion`.
13. **Every model call is labelled `provider="ollama"`.** `app.py` hard-codes the string, and the default config labels both the local container and Ollama Cloud `ollama`, so the two cannot be told apart or priced apart.
14. **Audit rows carry token counts but no cost**, and the admin UI shows tokens with no cost beside them.

The baseline specs already cover part of this. `retrieval-pipeline` "Per-stage token accounting" covers spans and token counters for model-calling stages. `smoke-testing` "Observable smoke path" covers the collector check. Neither covers metrics endpoints, cost, backends or dashboards. That justifies a new `observability` capability, plus deltas to those two requirements.

## Goals / Non-Goals

**Goals:**
- One connected trace per MCP tool call, searchable by `correlation_id` in Tempo.
- Every service scrapeable, with the standard metric families, including ingestion runs started from the CLI.
- Token and cost accounting for every model call that exists today, including ingestion embedding.
- Six provisioned dashboards, versioned as code and linted statically.
- The default dev stack, `make smoke` and the CI `stack` job stay as light and fast as they are now.

**Non-Goals:**
- A log backend (Loki), alerting (Alertmanager, rules), SLOs.
- Tracing or metrics for the Next.js admin UI.
- Spans for stages that do not exist yet (intent, enrichment, rerank, entitlement). Each later change adds its own.
- Production hardening: high availability, remote storage, TLS, Grafana single sign-on, per-tenant dashboard access.
- Exact provider billing reconciliation. Cost is an estimate from a configured table.

## Decisions

### D1. Backends: Prometheus, Tempo and Grafana; no Loki yet

| Service | Image (pinned) | Released | Why |
|---|---|---|---|
| Prometheus | `prom/prometheus:v3.15.1` | 2026-10-21 | Pull-based scraping matches the existing `/metrics` design; the de facto standard. |
| Tempo | `grafana/tempo:3.1.1` | 2026-10-21 | Accepts OTLP from the collector, local-disk storage, TraceQL search by span attribute (`correlation_id`). The current major line, chosen by the owner over the 2.10 patch line. |
| Grafana | `grafana/grafana:13.2.5` | 2026-10-27 | Native Prometheus and Tempo datasources, file provisioning. |
| Collector | `otel/opentelemetry-collector-contrib:0.123.0` (unchanged) | – | Already in use. A bump is unrelated to this change. |

Each tag is at least two weeks old and was checked to exist on Docker Hub on 2026-11-12. Tempo 3 changed parts of its configuration from 2.x, so `infra/tempo/tempo.yaml` is written against the 3.1 documentation and validated by starting the pinned image in `smoke-obs`, not copied from 2.x examples. Prometheus `v3.13.5` is a patched older line if the owner later prefers the longest-supported series.

**Loki is a follow-up change.** The services log unstructured text to stdout, and `docker compose logs` already serves that. Loki adds another 150 to 300 MB of RAM and a log-shipping path (collector `filelog` receiver or Docker driver), and it pays off once logs are structured and carry `trace_id`. The owner wants it, so a separate change, `add-log-aggregation`, will be proposed once this one merges: structured JSON logs with `trace_id` and `correlation_id` in every service, Loki in the same opt-in overlay, and Grafana links from a trace to its logs. Keeping it separate keeps this change reviewable and lets the log format be designed on its own.

*Alternatives:* **Jaeger** instead of Tempo (good UI, but a second UI next to Grafana, and Tempo's TraceQL by attribute fits the `correlation_id` lookup). **The OTel Collector's `prometheus` exporter, with no Prometheus** (it cannot hold history or serve dashboards over time). **Grafana LGTM all-in-one image** (`grafana/otel-lgtm`): one container, but it is aimed at demos, bundles Loki and Pyroscope we don't need, and hides the per-component config operators would need to move to production.

### D2. An opt-in overlay file, not part of the default `dev` profile

The backends live in `infra/compose/docker-compose.observability.yml`, applied with `-f`. This follows the existing `docker-compose.smoke.yml` and `docker-compose.e2e.yml` pattern. The new services carry `profiles: [dev]` like everything else, so `--profile dev` still selects them when the overlay is applied.

Reasons:
- **RAM.** The dev stack already runs Postgres with AGE, Qdrant, Valkey, Ollama with an embedding model, and four app services. Prometheus, Tempo and Grafana add an estimated 400 to 700 MB of resident memory. Many laptops running Docker Desktop already have a tight VM limit.
- **CI time.** The `stack` job runs the smoke and the Playwright e2e suite. Three more images to pull and start would add time to every PR for checks that most PRs don't affect.
- **Collector config must differ.** Sending traces to a Tempo that isn't there would make the collector log export errors in every batch, and the smoke greps the collector log. The overlay overrides the collector command to merge a second config file (`--config=…/otel-collector.yaml --config=…/otel-collector.tempo.yaml`). The collector merges multiple `--config` files, so the base file is reused unchanged. The merged file adds an `otlp/tempo` exporter and lists `[debug, otlp/tempo]` in the traces pipeline, so the existing smoke's log grep still works with the overlay applied.

Make targets: `make up-obs` (dev plus the overlay, detached), `make smoke-obs`, and `make down` gains `--remove-orphans` so overlay containers are removed even when the overlay is not passed.

*Alternatives:* **A separate `observability` compose profile in the main file.** Profiles can add services but cannot change the collector's command, so the Tempo export would need an env-var-driven exporter list, which is fragile. **Always on in `dev`**: simplest for users, but it pays the RAM and CI costs on every run. The owner chose opt-in.

**Documentation is part of the decision.** An opt-in feature that nobody can find is the same as a missing feature. So the opt-in nature is stated in every place a new user looks:
- README quickstart: an "Optional: observability" step after `make up-d`, with `make up-obs`, the Grafana URL, and one line on the RAM cost.
- README stack table: the telemetry row reads "OpenTelemetry → Collector → Tempo, Prometheus, Grafana (opt-in: `make up-obs`)".
- `docs/OPERATIONS.md`: an Observability section covering what the overlay adds, how to start and stop it, what keeps working without it (spans still reach the collector log; `/metrics` still serves), ports, login, retention, disk and RAM, the pricing table, and troubleshooting.
- `make help`: `up-obs` and `smoke-obs` described as optional.
- `.env.example`: the observability keys grouped under a comment saying they apply only with the overlay.

### D3. Ingestion metrics: Prometheus multiprocess mode

The ingestion server and the CLI processes started with `docker compose exec` run in the same container. Setting `PROMETHEUS_MULTIPROC_DIR` to a `tmpfs` mount (`/run/opencg-metrics`) makes every process write its counters to memory-mapped files there. The server's `/metrics` handler builds a `MultiProcessCollector` registry that sums them. Counters from exited CLI processes keep counting, which is exactly what is needed. The directory is cleared when the container starts, so values reset on restart, which Prometheus `rate()`/`increase()` handles.

Constraints this brings, which the implementation must respect:
- The shared module must build its metrics against the multiprocess-aware registry when the env var is set. The pipeline and MCP server keep the current single-process registry.
- Only counters and histograms are used. No gauges are needed today; if one is added later it must declare a `multiprocess_mode`.
- The directory must be emptied at container start (entrypoint `rm -rf "$PROMETHEUS_MULTIPROC_DIR"/*`), or stale files from a previous container could be counted.

*Alternatives:* **A Pushgateway** that CLI runs push to (another service, and the well-known stale-series problem). **OTLP metrics pushed to the collector**, with the collector exposing a Prometheus endpoint: this works and unifies the pipeline, but it moves the metrics source of truth away from the `/metrics` endpoints the spec and smoke already rely on, and it needs the collector in every test. **Route the CLI through the ingestion HTTP API**: this changes CLI behaviour and the smoke's bounded-exec design.

### D4. Trace propagation

- **MCP server**: add `@opentelemetry/sdk-trace-node`, `@opentelemetry/exporter-trace-otlp-http`, `@opentelemetry/api` and the W3C propagator. A small `telemetry.ts` sets the provider up at start-up, using the same env var and disable values as `setup_otel()`. Each tool handler runs inside a span `mcp.<tool>` (without the `opencg/` prefix) with `correlation_id`, `tool` and `tenant` attributes. `PipelineClient` injects `traceparent` and `tracestate` into its `undici` headers. Manual injection is used rather than auto-instrumentation: there are three call sites, and `undici.request` is not covered by the fetch instrumentation.
- **Pipeline**: extract the context with `opentelemetry.propagate.extract(request.headers)` in `/retrieve` (and the other routes the MCP server calls), and start `pipeline.retrieve` as a child of it. Manual extraction is preferred over `opentelemetry-instrumentation-fastapi`, which would add an extra server span per route and change the root span name operators already know. This is a recommendation, and either approach meets the spec.
- **`correlation_id` on every span**: set the attribute explicitly in a small `stage_span(name, correlation_id)` helper in `opencg_shared`. Baggage plus a span processor is an alternative, but explicit is easier to test with an in-memory exporter.
- **Model-call spans**: `OllamaEmbeddings.embed` and the chat client open `model.embed` / `model.chat` spans themselves, so every caller (retrieve, vector search, ingest, extraction) gets them for free. Provider errors are counted in the same place.
- `setup_otel()` reads `telemetry.otlp_endpoint` as a fallback when the env var is unset, so the config key stops being dead.

### D5. Metric additions and label rules

New families: `opencg_cost_usd_total{provider,model,tenant}`, `opencg_cost_unpriced_tokens_total{provider,model}`, `opencg_ingestion_runs_total{connector,status}`, `opencg_ingestion_documents_total{connector}`, `opencg_ingestion_chunks_total{connector}`, `opencg_ingestion_run_duration_seconds{connector}` and `opencg_audit_writes_total{log,outcome}`. Existing families are wired where they were missing (stage latency for every pipeline stage, provider errors, request error outcomes).

The cost counter keeps the vision's labels and does not add `stage`. Per-stage cost is available from `opencg_tokens_total` multiplied by the price, and in the usage envelope, and leaving `stage` out keeps cardinality down. `tenant` stays as a label, because the deployment is single-tenant today and the label set is bounded by configuration.

`outcome` on `opencg_requests_total` is `ok`, `error` (unhandled or upstream failure) or `rejected` (validation, auth, or later policy denial).

The MCP server uses `prom-client` with the default Node process metrics turned off, so its `/metrics` only shows `opencg_*` series. Process metrics are cheap to add later.

### D6. Provider labels and cost estimation

**One provider label per model endpoint.** The owner wants every LLM endpoint counted on its own. The `provider` field of each `providers.<role>` block is already in the config; this change makes it the single source of the `provider` label on tokens, cost, provider errors, spans and the usage envelope. Today the pipeline hard-codes `provider="ollama"` in `app.py`, and the default config labels both the local container and Ollama Cloud `ollama`. After this change:

- The checked-in `opencg.yaml` sets `providers.chat.provider: ollama-cloud`. Embeddings stay `ollama`.
- `ProviderEndpoint` resolves the label once at load: a `provider` of `ollama` whose `base_url` host is `ollama.com` (or a subdomain) becomes `ollama-cloud`, and the service logs that once. Older configs therefore get the right label with no edit.
- `ollama` and `ollama-cloud` both use the existing Ollama adapter. The label selects pricing and metrics, not the wire protocol. A later provider adapter (for example `anthropic` or `openai`) brings its own label.
- No call site passes a literal provider string. Each reads it from the endpoint it called.

**Pricing table.**

```yaml
observability:
  pricing:
    # USD per 1,000 tokens. A (provider, model) pair with no row is still
    # counted, in opencg_cost_unpriced_tokens_total, and shown as "unpriced".
    - provider: ollama
      model: nomic-embed-text
      input_usd_per_1k: 0
      output_usd_per_1k: 0
      source: "compose-local model; no charge"
      as_of: 2026-11-12
    - provider: ollama-cloud
      model: gemma4:31b
      input_usd_per_1k: <published rate>
      output_usd_per_1k: <published rate>
      source: https://ollama.com/pricing
      as_of: <date checked>
```

- **Everything that has a price is priced.** Ollama Cloud moved to per-token billing on 2026-08-31 and publishes rates per model at ollama.com/pricing. The default table carries every model on that list (standard input and output rates; cached-input and off-peak discounts are not modelled), checked on 2026-11-12. The previous default chat model `gemma3:4b` is **not** on the list, so the owner moved the default to `gemma4:31b` (listed as `gemma4`, $0.14 / $0.40 per million input / output tokens) on 2026-11-12. A model missing from the list still shows as unpriced, never as free.
- `source` and `as_of` are required on every row, so a reader can tell where a number came from and how old it is. The OPERATIONS runbook explains how to refresh them.
- A small `pricing.py` in `opencg_shared` loads the table into a dict keyed by `(provider, model)` and exposes `cost_usd(provider, model, tokens_in, tokens_out)`, which returns `None` for an unpriced pair. `record_stage_tokens()` calls it, so every existing call site gains cost without changes, and returns the cost so the usage envelope and audit row use the same number.
- **Unpriced is not zero.** Metrics count unpriced tokens separately. The envelope, the audit row and the admin UI carry `null` and display "unpriced". `estimated_cost_usd` sums the priced entries only and sets `cost_complete: false` when any entry is unpriced.
- Floats are fine for a Prometheus counter and an estimate. The envelope rounds to 6 decimal places. The audit column is `NUMERIC(12,6)`.
- Prices are read at start-up. Changing a price never rewrites history, because counters only ever go up and audit rows are immutable.

*Alternatives:* **Prices in the database with an admin UI** (more moving parts than an estimate needs). **Fetching provider price lists at runtime** (network dependency, no stable API, and not available for local models). **Computing cost only in Grafana** from tokens multiplied by a constant per model (no cost in the usage envelope, audit trail or admin UI, and dashboards must be edited for every price change). **Treating unpriced as zero** (hides gaps; rejected).

### D7. Dashboards as code

- `infra/grafana/provisioning/datasources/datasources.yaml`: Prometheus (`uid: opencg-prometheus`, default) and Tempo (`uid: opencg-tempo`, with trace-to-metrics linking back to Prometheus).
- `infra/grafana/provisioning/dashboards/opencg.yaml`: a file provider with `folder: openCG`, `allowUiUpdates: false`, and `disableDeletion: true`.
- `infra/grafana/dashboards/`: `opencg-requests.json`, `opencg-stages.json`, `opencg-tokens-cost.json`, `opencg-ingestion.json`, `opencg-audit.json`, `opencg-providers.json`. Each has a fixed `uid` and a `tenant` template variable. The requests dashboard links each panel to a Tempo TraceQL search.
- The JSON is hand-authored or exported from Grafana and then normalised (sorted keys, `id: null`, no `version`), so diffs stay readable. A plain-JSON approach is chosen over Grafonnet or the Grafana Foundation SDK: no extra toolchain in a Python/TS repo, and contributors can export from the UI.
- `scripts/check-dashboards.py`, run in `make ci-static`, checks each file: valid JSON, a `uid`, datasource UIDs in the allowed set, and every `opencg_\w+` in a PromQL expression (with `_bucket`, `_count`, `_sum` and `_total` suffixes handled) defined in `opencg_shared.metrics`. The same script runs `promtool check config` through the pinned Prometheus image when Docker is available.
- Grafana runs with `GF_SECURITY_ADMIN_PASSWORD=${OPENCG__GRAFANA__ADMIN_PASSWORD:-admin}`, `GF_AUTH_ANONYMOUS_ENABLED=false` (owner decision: no anonymous viewing, even on loopback), analytics and update checks off, and the port bound to loopback like every other service. The host port defaults to 3030 (`OPENCG__GRAFANA__HOST_PORT`), not Grafana's usual 3000 (the admin UI) or 3001 (the e2e overlay's gated admin UI). `smoke-obs` asserts that an unauthenticated dashboard request is refused.

### D8. Retention and storage

- Prometheus: `--storage.tsdb.retention.time=${OPENCG__PROMETHEUS__RETENTION:-7d}` and `--storage.tsdb.retention.size=2GB`, a 15 s scrape interval, and a named volume `prometheus-data`.
- Tempo: local backend, 48 h block retention (in Tempo 3 the compaction block is read by the in-process backend scheduler and worker, so it is set as `backend_scheduler.provider.compaction.compaction.block_retention` and `backend_worker.compaction.block_retention`; 2.x's `compactor:` block no longer exists), named volume `tempo-data`. The OTLP gRPC receiver is internal only. Only the HTTP query API (3200) is published.
- Grafana: SQLite in the named volume `grafana-data`. It holds only users and preferences, because dashboards come from files.
- `make down-v` removes all three volumes, like the existing ones.

### D9. Verification

- **Unit tests**: pricing maths and unpriced handling; `record_stage_tokens` cost pairing; the multiprocess registry summing two processes (write from a subprocess, scrape in the parent); propagation (an in-memory span exporter in the pipeline tests asserts that `pipeline.retrieve` takes the parent from a given `traceparent` and that every span has `correlation_id`); the MCP server (vitest with an in-memory exporter asserts the `mcp.retrieve_for_context` span and that the outgoing `traceparent` header is present); the usage envelope sums; and the dashboard lint.
- **Default smoke** (unchanged footprint): scrape the three `/metrics` endpoints with `curl` and assert the families. Record `opencg_tokens_total{stage="ingest_embed"}` before and after ingestion. Fix the stale scenario name.
- **`make smoke-obs`**: runs the default smoke with both overlays, then polls with bounded waits: Prometheus `/api/v1/targets`, `/api/v1/query` for `increase(opencg_tokens_total[5m]) > 0` and the presence of the cost series, one MCP `retrieve_for_context` call over the HTTP transport (using `OPENCG__MCP__HTTP_TOKEN` when set), Tempo `/api/search?q={ span.correlation_id = "<id>" }`, then `/api/traces/<id>` to check the span names and the single `trace_id`, and Grafana `/api/search?folderUIDs=…` to compare against the files in `infra/grafana/dashboards/`.
- **CI**: the `stack` job does not run the overlay, so its duration is unchanged. A new `observability` job runs `make smoke-obs` on every pull request to `main`, on pushes to `main` and nightly, in parallel with `stack`. The owner made it a required check. It has **no path filter**: a required check that a path filter skips never reports, and GitHub then blocks the PR forever. It is added to `.github/rulesets/main-branch-protection.json`, and the live ruleset is updated with `gh api` only after the job has passed on `main`, so no open PR is blocked by a check that has never run. It uploads the compose logs and Prometheus target state as an artifact on failure.

### D10. Cost in the audit trail and the admin UI

The admin UI reads token counts from `opencg.audit_log` (`tokens_in`, `tokens_out`), not from Prometheus. To show cost wherever tokens are shown, the audit row has to carry it:

- `infra/postgres/init/060_audit_cost.sql` adds `estimated_cost_usd NUMERIC(12,6)` and `usage_by_provider JSONB`, both nullable. Rows written before the change stay `NULL`. Adding columns does not touch the immutability trigger, which forbids `DELETE` and every `UPDATE` other than flipping `legal_hold`.
- Existing deployments pick up the file through the same init-script path as the other tables. A fresh volume runs it. For an existing volume, OPERATIONS documents a one-line `psql -f` to apply it, because Postgres init scripts only run on an empty data directory. Checking whether the project already has a migration runner is task 2.8; if it has one, the change uses it instead.
- `AuditStore.write` fills both columns from the usage envelope.
- Admin UI: `TokenBar` gains an optional cost line, and a new `CostBreakdown` component lists `by_provider`. Both get stories, per the admin-ui conventions. The queries list, the audit detail page and the vector search result show cost. The display rules are: a dollar figure to 4 significant places, "unpriced" when any provider in the row is unpriced, and "—" for rows written before the change.
- The vector search route (`/search/vector`) returns the same `cost_usd` and provider fields as `/retrieve`.

## Risks / Trade-offs

- **The opt-in overlay can rot unnoticed** → path-filtered and nightly `smoke-obs` CI, and the dashboard lint runs on every PR.
- **Multiprocess-mode pitfalls** (stale files, gauge semantics) → a tmpfs directory cleared at start, no gauges, and a unit test across two processes.
- **Label cardinality** from `model` values as operators swap models → bounded by configuration. Labels never carry request data, and the spec forbids unbounded labels.
- **`/metrics` without authentication** exposes tenant and model names → bound to loopback by default, like every port. This must be revisited together with the identity and OPA work before any non-dev deployment.
- **The cost estimate drifts from real bills** → documented as an estimate. The unpriced counter makes gaps visible, and the table is under operator control.
- **Grafana's default `admin` password** → loopback binding, documented in OPERATIONS.md, and overridable through `.env`.
- **Collector multi-config merge behaviour** (lists are replaced, not appended) → the Tempo file restates the full traces pipeline exporter list. The smoke-obs check covers it.
- **Tempo 3 is a newer major line** with less community configuration to copy from → the config is written from the 3.1 docs, kept minimal (one receiver, local storage, retention), and proven by `smoke-obs` on every PR.
- **A required `observability` check makes every PR depend on three more images and a longer smoke** → it runs in parallel with `stack`, caches images like `stack` does, and retries image pulls. If it proves flaky, the fallback is to make it non-required through a follow-up change, not to skip it silently.
- **Published Ollama Cloud rates change** → each row records `source` and `as_of`; the OPERATIONS runbook says how to refresh it; past figures are not rewritten.
- **Relabelling Ollama Cloud chat from `ollama` to `ollama-cloud`** breaks saved queries that filter on the old value → nothing outside this repository reads these labels yet, and the CHANGELOG calls it out.

## Migration Plan

Everything is additive. Existing deployments see new `/metrics` endpoints, new span attributes and new envelope fields, and nothing breaks. Operators opt into the backends with `make up-obs`. Rollback means not applying the overlay. The instrumentation is harmless without the backends.

## Resolved Decisions (owner, 2026-11-12)

1. **Opt-in or default?** Opt-in overlay (D2). The documentation calls this out in the README quickstart, the README stack table, OPERATIONS.md, `make help` and `.env.example`.
2. **CI gating.** The `observability` job is a required check, run on every PR to `main` and nightly with no path filter (D9).
3. **Provider labels.** Every LLM endpoint gets its own provider label. Ollama Cloud chat is `ollama-cloud` (D6).
4. **Pricing.** Everything has token usage and pricing where a price is available. Ollama Cloud is priced at its published per-token rate. Anything without a price is shown as unpriced, never as free (D6, D10).
5. **Tempo line.** Tempo 3 (`grafana/tempo:3.1.1`) (D1).
6. **Grafana access.** No anonymous access (D7).
7. **Loki.** Wanted, as a follow-up change `add-log-aggregation` once this one merges (D1).

## Open Questions

None remaining. The Ollama Cloud rate for the default chat model is looked up at implementation time (task 1.1), not decided here.
