## 1. Shared telemetry foundations (`packages/shared-py`, `packages/shared`)

- [x] 1.1 Add `observability.pricing` to `openCGConfig` (list of `{provider, model, input_usd_per_1k, output_usd_per_1k, source, as_of}`, with `source` and `as_of` required). Default `opencg.yaml` rows: `ollama`/`nomic-embed-text` at zero, and `ollama-cloud`/`gemma3:4b` at the rate published on ollama.com/pricing on the day of implementation (record the URL and date; if that model has no published rate, leave the row out and note it in the PR)
- [x] 1.1a Provider labels: resolve `provider: ollama` + an `ollama.com` base URL to `ollama-cloud` in `ProviderEndpoint` (log once); set `providers.chat.provider: ollama-cloud` in `opencg.yaml`; unit tests for the default, legacy-block and legacy-Cloud cases
- [x] 1.2 Add `opencg_shared/pricing.py` with `cost_usd(provider, model, tokens_in, tokens_out)` returning `None` for an unpriced pair, one warning per unpriced pair per process, and unit tests (priced, zero-priced, unpriced is `None` not 0, rounding, missing `source`/`as_of` rejected)
- [x] 1.3 Extend `metrics.py`: new families from design D5; `record_stage_tokens()` also increments `opencg_cost_usd_total` or `opencg_cost_unpriced_tokens_total` and returns the cost; helpers `observe_stage()`, `record_provider_error()`, `record_audit_write()`, `record_ingestion_run()`
- [x] 1.4 Multiprocess support in `metrics.py`: when `PROMETHEUS_MULTIPROC_DIR` is set, build metrics for multiprocess mode and make `metrics_app` serve a `MultiProcessCollector` registry; unit test that a counter incremented in a subprocess shows up in the parent's scrape
- [x] 1.5 `otel.py`: fall back to `telemetry.otlp_endpoint` when the env var is unset; add a `stage_span(tracer, name, correlation_id, **attrs)` helper; add a W3C context-extraction helper; unit tests with an in-memory span exporter
- [x] 1.6 Usage envelope: add `ProviderUsage`, `UsageEnvelope.by_provider`, `UsageEnvelope.estimated_cost_usd`, `UsageEnvelope.cost_complete`, `StageUsage.cost_usd` (nullable) to the Python types and their TS mirrors in `packages/shared`; unit tests for defaults, serialisation and the unpriced case

## 2. Pipeline instrumentation (`services/pipeline`)

- [x] 2.1 Continue an incoming `traceparent` on `/retrieve` and the other routes the MCP server calls; set `correlation_id` on every stage span through `stage_span`
- [x] 2.2 Observe `opencg_stage_latency_seconds` for `identity`, `hybrid_retrieval`, `assemble` and `vector_search`
- [x] 2.3 Open `model.embed` / `model.chat` child spans inside the embeddings and chat clients, with `provider`, `model`, `tokens_in`, `tokens_out`, `latency_ms`, `cost_usd`; increment `opencg_provider_errors_total` on HTTP errors and timeouts
- [x] 2.4 Count `opencg_requests_total{outcome="error"|"rejected"}` on failure paths (exception handler around `/retrieve`; 4xx validation as `rejected`)
- [x] 2.5 Increment `opencg_audit_writes_total{log="retrieval"}` in `AuditStore.write` and `{log="graph"}` on graph audit writes, with `outcome` for success or failure
- [x] 2.6 Build `usage.by_provider`, `usage.estimated_cost_usd` and `usage.cost_complete` from the costs returned by `record_stage_tokens`, on `/retrieve` and `/search/vector`
- [x] 2.6a Replace every hard-coded `provider="ollama"` (`app.py` spans, `StageUsage`, `record_stage_tokens`) with the label of the endpoint that served the call; grep-based unit test that no pipeline or ingestion module passes a literal provider string
- [x] 2.7 Unit tests: span parentage from a given `traceparent`, `correlation_id` on every span, stage histogram counts, provider-error counter, error outcome, audit counter (fake `_Pool`/`_Conn` pattern), envelope sums match, unpriced entry gives `cost_complete: false`
- [x] 2.8 Audit cost: check whether the project has a migration path for existing volumes; add `infra/postgres/init/060_audit_cost.sql` (`estimated_cost_usd NUMERIC(12,6)`, `usage_by_provider JSONB`, both nullable); `AuditStore.write` fills them; admin audit routes return them; test that the immutability trigger still rejects an `UPDATE` of the new columns

## 3. Ingestion instrumentation (`services/ingestion`)

- [x] 3.1 Mount `/metrics` on the ingestion FastAPI app
- [x] 3.2 Compose: `tmpfs` at `/run/opencg-metrics` for the ingestion service, `PROMETHEUS_MULTIPROC_DIR` set for the server and for `exec`'d CLI processes, and the directory cleared at container start
- [x] 3.3 Record `stage="ingest_embed"` tokens and cost for every successful chunk embedding in `pipeline_runner.py`
- [x] 3.4 Record `opencg_ingestion_runs_total`, `_documents_total`, `_chunks_total` and `_run_duration_seconds` per connector for both CLI and HTTP runs; set `correlation_id` (the run ID) on ingestion spans
- [x] 3.5 Unit tests: embed tokens counted, run counters on success and failure, and the `/metrics` route serving the multiprocess registry

## 4. MCP server instrumentation (`services/mcp-server`)

- [x] 4.1 Add the pinned OTel and `prom-client` dependencies; add `src/telemetry.ts` (tracer provider, OTLP/HTTP exporter, the same disable values as `setup_otel`, service name `opencg-mcp-server`)
- [x] 4.2 Wrap each tool handler in an `mcp.<tool>` span with `correlation_id`, `tool` and `tenant`; record `opencg_requests_total{tool,outcome}` and `opencg_stage_latency_seconds{stage="mcp"}`
- [x] 4.3 Inject `traceparent` / `tracestate` into every `PipelineClient` request
- [x] 4.4 Serve unauthenticated `GET /metrics` next to `/healthz` / `/readyz` (default Node process metrics off)
- [x] 4.5 Vitest: span emitted with attributes (in-memory exporter), outgoing `traceparent` header present, `/metrics` reachable without the bearer token while `/mcp` still requires it, error outcome counted

## 4a. Admin UI cost display (`services/admin-ui`)

- [x] 4a.1 Extend the audit and vector-search types with `estimated_cost_usd`, `usage_by_provider` / `by_provider` and `cost_complete`
- [x] 4a.2 `TokenBar` gains an optional cost line; new `CostBreakdown` component (provider, model, tokens, cost, "unpriced"); stories for priced, partly unpriced and pre-change ("—") cases; vitest unit tests
- [x] 4a.3 Show cost on the queries list rows, the `/queries/<id>` detail page and the `/vectors` search result
- [x] 4a.4 Playwright e2e: the detail page and `/vectors` show a cost and a per-provider row after a live retrieval; the queries list shows a cost column

## 5. Observability backends (`infra/`)

- [x] 5.1 `infra/otel/otel-collector.tempo.yaml`: `otlp/tempo` exporter and traces pipeline `[debug, otlp/tempo]`; expose the collector's own metrics on 8888 (internal only)
- [x] 5.2 `infra/prometheus/prometheus.yml`: 15 s scrape of pipeline, ingestion, mcp-server, otel-collector and tempo; validated with `promtool check config`
- [x] 5.3 `infra/tempo/tempo.yaml` written against the Tempo 3.1 docs: OTLP gRPC receiver (internal), local storage, 48 h block retention, HTTP API on 3200
- [x] 5.4 `infra/compose/docker-compose.observability.yml`: `prom/prometheus:v3.15.1`, `grafana/tempo:3.1.1`, `grafana/grafana:13.2.5` (Grafana with `GF_AUTH_ANONYMOUS_ENABLED=false`), healthchecks, named volumes, ports `${OPENCG__BIND_ADDRESS:-127.0.0.1}:${OPENCG__<SERVICE>__HOST_PORT:-default}` (Grafana 3030, not 3001, which the e2e overlay's gated admin UI uses; Prometheus 9090; Tempo 3200), retention from `OPENCG__PROMETHEUS__RETENTION`, and the collector command override merging both configs
- [x] 5.5 Makefile: `up-obs`, `smoke-obs`, and `down` / `down-v` with `--remove-orphans`; `make help` text marking `up-obs` and `smoke-obs` as optional
- [x] 5.6 `.env.example`: a block headed "Observability (only used with `make up-obs`)" with commented `OPENCG__GRAFANA__HOST_PORT`, `OPENCG__GRAFANA__ADMIN_PASSWORD`, `OPENCG__PROMETHEUS__HOST_PORT`, `OPENCG__PROMETHEUS__RETENTION`, `OPENCG__TEMPO__HOST_PORT`
- [x] 5.7 Measure resident memory of the three backends on the reference stack after `smoke-obs`, and record it here and in OPERATIONS.md (2026-11-12: Tempo ~340 MB, Grafana ~260 MB, Prometheus ~70 MB; ~670 MB total)

## 6. Grafana dashboards as code

- [x] 6.1 Provisioning: `infra/grafana/provisioning/datasources/datasources.yaml` (`opencg-prometheus`, `opencg-tempo` with trace-to-metrics) and `infra/grafana/provisioning/dashboards/opencg.yaml` (folder "openCG", `allowUiUpdates: false`)
- [x] 6.2 Dashboards: `opencg-requests.json`, `opencg-stages.json`, `opencg-tokens-cost.json`, `opencg-ingestion.json`, `opencg-audit.json`, `opencg-providers.json` with fixed UIDs, a `tenant` variable, and normalised JSON
- [x] 6.3 `scripts/check-dashboards.py` (JSON validity, `uid`, allowed datasource UIDs, `opencg_*` metric names exist in `opencg_shared.metrics`) wired into `make ci-static`, with a unit test using a deliberately broken fixture
- [x] 6.4 Manually check every panel renders data after `make smoke-obs`, and attach screenshots to the PR (2026-11-12: all six render; only the error, rejection and provider-error panels show "No data", because no errors occurred)

## 7. Smoke and CI

- [x] 7.1 Default smoke: scrape the three `/metrics` endpoints and assert each service's required families; assert `opencg_tokens_total{stage="ingest_embed"}` increased; keep the `/metrics` checks in offline-exporter mode
- [x] 7.2 `smoke-obs` mode in `tests/smoke/run.sh` (helpers in `lib.sh`): apply both overlays; bounded checks for Prometheus targets, token increase and cost series, an MCP `retrieve_for_context` call over HTTP, the Tempo trace by `correlation_id` (span names and a single `trace_id`), the Grafana dashboard list compared with the files, and Grafana refusing an unauthenticated request (401)
- [ ] 7.3 Confirm each new smoke check fails red against a deliberately broken config (for example, Tempo exporter removed, ingestion `/metrics` unmounted), then green
- [x] 7.4 CI: add an `observability` job running `make smoke-obs` on every PR to `main`, pushes to `main` and nightly, with no path filter, in parallel with `stack`; upload compose logs and Prometheus target state on failure; confirm the `stack` job's duration is unchanged
- [ ] 7.5 Add `observability` to `.github/rulesets/main-branch-protection.json`; after the job has passed on `main`, apply the ruleset to the live repository with `gh api` (confirm with the owner before running it) and check an open PR shows the new required check

## 8. Documentation

- [x] 8.1 `docs/OPERATIONS.md` Observability section, opening with a callout that the backends are opt-in: what the overlay adds, `make up-obs` and how to stop it, what keeps working without it, ports table rows, Grafana login, finding a trace by `correlation_id`, the metric catalogue, the pricing table (provider labels, `source`/`as_of`, how to refresh rates) and unpriced handling, applying `060_audit_cost.sql` to an existing volume, retention and disk, RAM cost, multiprocess metrics directory, troubleshooting (targets down, no traces)
- [x] 8.2 README: stack table row ("OpenTelemetry → Collector → Tempo, Prometheus, Grafana (opt-in: `make up-obs`)"), the "Not in v0" list (Loki listed as planned), and an "Optional: observability" quickstart step with `make up-obs`, the Grafana URL and login, and the extra RAM
- [x] 8.3 CHANGELOG entry (including the `ollama` → `ollama-cloud` label change for Cloud chat); update AGENTS.md / CLAUDE.md / `.cursor/rules/opencg.mdc` stack table, the required-checks sentence (adding `observability`) and the "where stuff lives" tree for `infra/grafana`, `infra/prometheus`, `infra/tempo` (keeping the three files identical)

## 9. Verification and close-out

- [x] 9.1 `make ci-static` green (lint, typecheck, unit tests, dashboard lint, `openspec validate add-observability-stack --strict`)
- [x] 9.2 `make smoke` and `make e2e` green on the default stack; `make smoke-obs` green on the overlay stack
- [x] 9.3 Run the secrets grep from AGENTS.md on the staged diff; confirm no `.env` changes are staged
- [ ] 9.4 Note in `add-foundation` follow-up tracking which parts of its observability spec are delivered and which are deferred (spans for future stages, alerting)
- [ ] 9.4a Scaffold the follow-up change `add-log-aggregation` (structured JSON logs with `trace_id` and `correlation_id`, Loki in the overlay, trace-to-logs links) and bring it to the owner for approval
- [ ] 9.5 After merge: `openspec archive add-observability-stack`
