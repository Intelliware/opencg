# Operations

Operational runbook for the v0 stack (see [`bootstrap-thin-mvp`](../openspec/changes/archive/2026-11-10-bootstrap-thin-mvp/proposal.md) for the authoritative contract).

## Bringing the stack up

```bash
cp .env.example .env
make up-d    # build + start in the background
make ps      # check status
make logs    # follow combined logs
make down    # stop (keeps volumes); also removes the optional observability containers
make down-v  # stop + DELETE volumes (loses everything, incl. Prometheus/Tempo/Grafana data)
```

Prometheus, Tempo and Grafana are **not** started by `make up-d`. They are an optional overlay you turn on with `make up-obs`; see [Observability](#observability).

First start downloads the Postgres+AGE image, the Qdrant image, the Valkey image, and the Ollama image, and then pulls the configured embedding model (~270 MB for `nomic-embed-text`). Expect 3–5 minutes on a typical laptop.

## Network exposure and host ports

Every published port binds to `OPENCG__BIND_ADDRESS`, which defaults to `127.0.0.1`, so nothing is reachable from other machines unless you change it. Set it to `0.0.0.0` only on purpose, and only after setting real passwords and tokens (see [`SECURITY.md`](../SECURITY.md)). The pipeline and ingestion APIs have no authentication of their own.

Each host port can be moved in `.env` to dodge a collision; the container ports never change:

| Service | Variable | Default host port | Container port |
|---|---|---|---|
| Admin UI | `OPENCG__ADMIN_UI__HOST_PORT` | 3000 | 3000 |
| Pipeline | `OPENCG__PIPELINE__HOST_PORT` | 8000 | 8000 |
| Ingestion | `OPENCG__INGESTION__HOST_PORT` | 8100 | 8100 |
| MCP server (HTTP `/mcp` and health) | `OPENCG__MCP__HOST_PORT` | 8181 | 8080 |
| Postgres | `OPENCG__POSTGRES__HOST_PORT` | 5432 | 5432 |
| Qdrant HTTP / gRPC | `OPENCG__QDRANT__HOST_PORT` / `OPENCG__QDRANT__GRPC_HOST_PORT` | 6333 / 6334 | 6333 / 6334 |
| Valkey | `OPENCG__VALKEY__HOST_PORT` | 6379 | 6379 |
| Ollama | `OPENCG__OLLAMA__HOST_PORT` | 11435 | 11434 |
| OTel Collector OTLP HTTP / health | `OPENCG__OTEL__HTTP_HOST_PORT` / `OPENCG__OTEL__HEALTH_HOST_PORT` | 4318 / 13133 | 4318 / 13133 |
| Gated admin UI (e2e overlay only) | `OPENCG__ADMIN_UI_GATED__HOST_PORT` | 3001 | 3000 |
| Grafana (observability overlay only, `make up-obs`) | `OPENCG__GRAFANA__HOST_PORT` | 3030 | 3000 |
| Prometheus (observability overlay only) | `OPENCG__PROMETHEUS__HOST_PORT` | 9090 | 9090 |
| Tempo query API (observability overlay only) | `OPENCG__TEMPO__HOST_PORT` | 3200 | 3200 |

Ollama defaults to 11435 so it doesn't shadow a native Ollama app on 11434. The `curl` examples below use the default ports; substitute yours if you moved them. `make smoke` and `make e2e` read the same variables from `.env`.

## Admin UI access gate

By default the admin UI has no login. Every page shows an "Unauthenticated mode — local use only" banner, and the server logs a warning at startup. Set a shared password to require a sign-in:

```bash
# .env
OPENCG__ADMIN_UI__PASSWORD=<a long random password>
```

Restart the admin UI (`make up-d` recreates it). Every page and `/api/proxy/**` route then needs a session: pages redirect to `/login`, and API calls get `401`. `/login`, `/api/auth/*`, `/api/healthz` and static files stay open. Sessions last 12 hours, and changing the password signs everyone out. A sign-out button appears in the sidebar.

This is a stopgap (`REPLACE-BEFORE-PROD`): one shared password, no per-user accounts. Put TLS in front of it (a reverse proxy) before using it over a network; the session cookie is marked `Secure` when the request, or the proxy's `x-forwarded-proto`, is HTTPS.

## Configuration

A single `opencg.yaml` file is the source of truth. Environment variables override file values using the convention `OPENCG__<SECTION>__<KEY>` (double underscore separates nesting levels). Copy `.env.example` to `.env` and edit; the compose stack mounts `.env` into every service.

| Key | Default | Notes |
|---|---|---|
| `OPENCG__TENANT` | `default` | Single-tenant deploy slug. |
| `OPENCG__IDENTITY__PRINCIPAL` | `local-dev` | Stubbed identity. Replace before any non-dev deploy. |
| `OPENCG__IDENTITY__ROLES` | `admin,reader` | Comma-separated list. |
| `OPENCG__POSTGRES__USER` / `__PASSWORD` / `__DB` | `opencg` / `opencg` / `opencg` | Compose creates the database with these and derives `OPENCG__POSTGRES__URL` from them. **Change the password** for anything beyond local use. It only takes effect when the volume is first created, so change it before the first `make up-d`, or run `make down-v`. |
| `OPENCG__POSTGRES__URL` | derived | Set only to use an external database. |
| `OPENCG__QDRANT__URL` | `http://qdrant:6333` | Vector store. |
| `OPENCG__VALKEY__URL` | `redis://valkey:6379/0` | Cache (unused by v0). |
| `OPENCG__OLLAMA__BASE_URL` | `http://ollama:11434` | Compose-internal Ollama by default. |
| `OPENCG__OLLAMA__EMBEDDING_MODEL` | `nomic-embed-text` | See "Swapping the embedding model" below. |
| `OPENCG__PROVIDERS__CHAT__BASE_URL` | `https://ollama.com` | Chat endpoint used by text graph extraction. |
| `OPENCG__PROVIDERS__CHAT__MODEL` | `gemma3:4b` | Independently configurable extraction model. |
| `OPENCG__PROVIDERS__CHAT__API_KEY` | empty | Secret bearer token for the chat endpoint. |
| `OPENCG__RETRIEVAL__DEFAULT_TOP_K` | `20` | Per-leg retrieval limit. |
| `OPENCG__RETRIEVAL__DEFAULT_TOKEN_BUDGET` | `4000` | Assemble-stage hard cap. |

## Extraction model

Two paths share the same chunk → embed → upsert orchestration but differ on what becomes a chunk:

- **Code files** (`.py`, `.ts`, `.go`, `.rs`, `.kt`, ... — anything in graphifyy's tree-sitter dispatch except markdown/yaml/json/html) are processed by `chunk_code_by_symbols`. Each AST symbol (class / function / method) becomes one chunk. The same graphifyy call produces the **deterministic code graph** that lands in `opencg.concept` / `opencg.relationship_edge` as `confirmed` state. Powered by [graphifyy](https://github.com/safishamsi/graphify).
- **Text files** (`.md`, `.yaml`, `.toml`, `.json`, ...) flow through `chunk_text` (paragraph splitter). A best-effort chat-model pass extracts candidate concepts and named relationships after the catalog and vector writes succeed.

Code extraction emits `pipeline.graph_extract_code` with zero model tokens. Text extraction emits `pipeline.graph_extract_text`, token counts, latency, accepted-edge counters, and error counters. Provider errors, malformed output, and timeouts are logged and counted but never abort ingestion.

## Knowledge graph

Open `/graph` to search concepts, inspect evidence and neighbours, review candidate edges, and edit the relationship vocabulary. The seven seeded semantic relationship names are `depends_on`, `defined_in`, `supersedes`, `mentions`, `related_to`, `causes`, and `derived_from`. Graphifyy also uses the code-specific `calls`, `imports`, and `uses` names.

Text extraction is controlled by:

| Key | Default | Effect |
|---|---|---|
| `OPENCG__PROVIDERS__EXTRACTION__ENABLED` | `true` | Enables best-effort text extraction during ingest and re-extract. |
| `OPENCG__PROVIDERS__EXTRACTION__MIN_CONFIDENCE` | `0.6` | Drops model relationships below this confidence. |
| `OPENCG__PROVIDERS__EXTRACTION__TIMEOUT_SECONDS` | `30` | Per-chunk chat request deadline. |
| `OPENCG__PROVIDERS__EXTRACTION__CHAT_QPS` | empty | Reserved rate limit; empty means unbounded. |

The active prompt and JSON response contract are documented in [`EXTRACTOR_PROMPT.md`](./EXTRACTOR_PROMPT.md).

## Ingestion

A single connector ships today: `git`. Trigger an ingest from any of:

```bash
# 1. From the host
make ingest-git REPO=https://github.com/anthropics/anthropic-cookbook

# 2. From the admin UI
open http://localhost:3000/ingestion   # use the "Run now" form

# 3. From the pipeline API (which proxies to the ingestion service)
curl -X POST http://localhost:8000/ingestion/git/run \
  -H 'content-type: application/json' \
  -d '{"repo_url":"https://github.com/anthropics/anthropic-cookbook"}'

# 4. Direct CLI inside the ingestion container
docker compose -f infra/compose/docker-compose.yml exec ingestion \
  uv run --package opencg-ingestion \
  python -m opencg_ingestion.cli git <repo-url>
```

URLs submitted through the admin UI or the HTTP API (options 2 and 3) are checked before cloning. They must be `https://`, `ssh://`, `git://` or `user@host:path`, must not embed a password or start with `-`, and must resolve to a public address. Local paths are refused unless they sit under a directory in `OPENCG__INGESTION__GIT__LOCAL_ROOTS`. `OPENCG__INGESTION__GIT__ALLOWED_HOSTS` lists internal git hosts that may resolve to private addresses. The CLI (options 1 and 4) is operator-driven and not restricted.

Re-ingest is idempotent (entities are upserted by stable ID derived from `(tenant, source_uri)`). Run history (from options 2 and 3) is in-memory inside the ingestion container — restarting clears it. A follow-up change adds durable history.

Re-run text graph extraction without re-embedding:

```bash
docker compose -f infra/compose/docker-compose.yml exec ingestion \
  uv run --package opencg-ingestion \
  python -m opencg_ingestion.cli re-extract

# Optional catalog filters
docker compose -f infra/compose/docker-compose.yml exec ingestion \
  uv run --package opencg-ingestion \
  python -m opencg_ingestion.cli re-extract --source git --since 2026-06-01
```

Chunks already processed by the current extractor version are skipped. Failures are counted and the command continues with later chunks.

### Bounded ingestion

The Git CLI accepts optional positive limits for diagnostics and provider
canaries. Normal ingestion remains unlimited when these options are omitted:

```bash
docker compose -f infra/compose/docker-compose.yml exec ingestion \
  uv run --package opencg-ingestion \
  python -m opencg_ingestion.cli git <repo-url> \
  --max-documents 1 --max-chunks 2
```

### Full smoke and cloud canary

`make smoke` is deterministic and does not call a paid chat provider. It
constructs a uniquely named local Git repository from the committed fixture,
uses the real local embedding model and a compose-local Ollama-compatible chat
stub, verifies current-run vector/graph/audit records and OTel spans, and
terminates after 300 seconds by default.

```bash
make smoke
SMOKE_TIMEOUT_SECONDS=180 make smoke
```

The real-provider canary is explicit and bounded to one document and two
chunks:

```bash
make smoke-cloud
```

It requires `OPENCG__PROVIDERS__CHAT__BASE_URL`,
`OPENCG__PROVIDERS__CHAT__MODEL`, and
`OPENCG__PROVIDERS__CHAT__API_KEY` in `.env`.

The smoke also scrapes `/metrics` on the pipeline, the ingestion service and
the MCP server (it makes one MCP `retrieve_for_context` call over HTTP, sending
`OPENCG__MCP__HTTP_TOKEN` when it is set), fails if a required metric family is
missing, and checks that ingestion's `opencg_tokens_total{stage="ingest_embed"}`
went up. These checks need no Prometheus, Tempo or Grafana.

The dev stack includes an OpenTelemetry Collector at
`http://otel-collector:4318`. Set `OTEL_EXPORTER_OTLP_ENDPOINT=none` for an
explicit offline run; smoke reports that trace verification was skipped. The
`/metrics` checks still run in that mode.

`make smoke-obs` is the optional observability smoke: it applies the
observability overlay as well, runs the same smoke, then checks Prometheus,
Tempo and Grafana (see [Observability](#observability)).

### Test overlays (smoke and e2e)

The default stack (`make up-d`) runs only what a real deployment needs. Test wiring lives in two compose overlays that the test commands apply for you:

- `infra/compose/docker-compose.smoke.yml` (`make smoke`, `make smoke-cloud`, `make e2e`) adds the deterministic `smoke-chat` stub, mounts the committed fixture into ingestion, and allows local repository paths under `/tmp`.
- `infra/compose/docker-compose.e2e.yml` (`make e2e` only) points ingestion's extraction at `smoke-chat`, so a "Run now" from the UI never calls a provider, and starts `admin-ui-gated`, a second admin UI with the access gate on.

A third overlay, `infra/compose/docker-compose.observability.yml`, is not a test overlay: it is the optional Prometheus, Tempo and Grafana stack, applied by `make up-obs` and `make smoke-obs` only (see [Observability](#observability)).

After the e2e suite, its teardown removes `admin-ui-gated` and `smoke-chat` and recreates ingestion with your `.env` settings. Set `E2E_KEEP_OVERLAY=1` to skip that between runs. After `make smoke`, ingestion keeps the smoke overlay (the fixture mount and `/tmp` local roots) until it is next recreated, for example by `make up-d`.

## Vector search

`POST /search/vector` runs the same embeddings + Qdrant path the retrieve pipeline uses but writes no audit row — it is admin/operator exploration. Hit it from the admin UI at `/vectors` or directly:

```bash
curl -X POST http://localhost:8000/search/vector \
  -H 'content-type: application/json' \
  -d '{"query":"prompt caching","top_k":20}'
```

Results are fused across every source collection by Reciprocal Rank Fusion. `top_k` is server-capped at 100.

## Entity browse and tombstone

Browse via the admin UI (`/entities` with filters) or directly:

```bash
# List with filters
curl "http://localhost:8000/entities?source=git&classification=internal&limit=50"

# Fetch a single entity with lineage (parent + chunks)
curl http://localhost:8000/entities/<entity_id>

# Soft delete (tombstone). Idempotent — re-tombstoning preserves the original timestamp.
curl -X DELETE http://localhost:8000/entities/<entity_id>
```

Tombstoning sets `tombstoned_at` on the catalog row, and from then on the entity is excluded from both retrieval legs (`/retrieve`, and so MCP) and from `/search/vector`. Qdrant points are not deleted: every vector hit is checked against the catalogue at query time, and the number dropped is recorded as the `tombstoned_filtered` span attribute. Re-ingesting the source clears the tombstone.

## Swapping the embedding model

The vector dimension is per-collection in Qdrant. If you change `embedding_model`, you must also change `qdrant.vector_size` in `opencg.yaml` to match the new model's output dim — and either recreate the Qdrant collections or stand up a fresh tenant.

| Model | Dimension | Notes |
|---|---|---|
| `nomic-embed-text` (default) | 768 | Fast on CPU. Good general baseline. |
| `bge-m3` | 1024 | Multilingual; larger. |
| `qwen3-embedding:8b` | 4096 | Heavy; needs ≥ 16 GB RAM in the Ollama container. |
| `embeddinggemma` | 768 | Google's small embed model. |

Procedure to swap (full reset):

```bash
make down-v
# Edit opencg.yaml: ollama.embedding_model AND qdrant.vector_size
# (also update .env's OPENCG__OLLAMA__EMBEDDING_MODEL)
make up-d
# First start re-pulls the new model.
make ingest-git REPO=<your repo>
```

In-place swap (preserves catalog rows but rebuilds vector points) is not yet supported; a `model-providers` follow-up change adds a re-embed CLI.

## Identity stub

v0 hardcodes an identity context from `.env`. Anything calling the MCP server gets the configured `principal` + `roles` + `tenant` attached. The pipeline propagates these to OPA (when it lands in the follow-up) and into every audit row. **Replace with real auth before any non-dev deployment** — the propagation contract is already in place so only the verifier needs to change.

## Observability

> **The observability backends are optional.** Prometheus, Tempo and Grafana are **not** part of the default stack. `make up-d`, `make smoke`, `make e2e` and the CI `stack` job never start them. Turn them on with `make up-obs`; turn them off with `make down`. They add about 700 MB of RAM.

### What works without the overlay

Every service is instrumented whether or not the backends run:

- **Traces.** The MCP server, the pipeline and the ingestion service export OpenTelemetry spans over OTLP/HTTP to the bundled collector, which prints them to its log (`docker compose -f infra/compose/docker-compose.yml logs otel-collector`). An MCP tool call and the pipeline work it triggers share one trace (`mcp.<tool>` → `pipeline.retrieve` → `pipeline.identity` / `pipeline.hybrid_retrieval` / `pipeline.assemble` → `model.embed` / `model.chat`), and every span carries `correlation_id`.
- **Metrics.** The pipeline (`:8000/metrics`), the ingestion service (`:8100/metrics`) and the MCP server (`:8181/metrics`) serve Prometheus text without authentication. `/metrics` on the MCP server works even when `OPENCG__MCP__HTTP_TOKEN` gates `/mcp`.
- **Usage and cost.** Every `/retrieve` and `/search/vector` response carries a `usage` envelope with per-stage tokens, `by_provider`, `estimated_cost_usd` and `cost_complete`. The retrieval audit row stores the same cost, and the admin UI shows it beside every token count.

Without the overlay nothing stores the spans or charts the metrics over time.

### What the overlay adds

`infra/compose/docker-compose.observability.yml` adds three services and changes one:

| Service | Image | What it does |
|---|---|---|
| Prometheus | `prom/prometheus:v3.15.1` | Scrapes the pipeline, ingestion, MCP server, collector and Tempo every 15 s ([`infra/prometheus/prometheus.yml`](../infra/prometheus/prometheus.yml)). |
| Tempo | `grafana/tempo:3.1.1` | Stores traces (monolithic mode, local disk; [`infra/tempo/tempo.yaml`](../infra/tempo/tempo.yaml)). Its OTLP receiver is compose-internal; only the query API is published. |
| Grafana | `grafana/grafana:13.2.5` | Six provisioned dashboards in an "openCG" folder ([`infra/grafana/`](../infra/grafana/)). |
| OTel Collector (changed) | unchanged image | Also loads [`infra/otel/otel-collector.tempo.yaml`](../infra/otel/otel-collector.tempo.yaml): exports traces to Tempo as well as to its log, and serves its own metrics on `:8888` (internal only). |

### Turning it on and off

```bash
make up-obs        # dev stack + overlay, detached; waits for health
open http://localhost:3030   # Grafana (admin / admin unless you set a password)
make smoke-obs     # optional: smoke + Prometheus/Tempo/Grafana checks
make down          # stops everything, overlay containers included (keeps volumes)
make down-v        # also DELETES the prometheus-data, tempo-data and grafana-data volumes
```

`make down` always passes the overlay file and `--remove-orphans`, so it removes the overlay's containers whether or not you started them. Running plain `make up-d` while the overlay is up switches the collector back to its default config (log only) and leaves Prometheus, Tempo and Grafana running as orphans; run `make down` or `make up-obs` to get back to a consistent state.

| Port | Variable | Default | Notes |
|---|---|---|---|
| Grafana | `OPENCG__GRAFANA__HOST_PORT` | 3030 | Not 3000 (admin UI) or 3001 (the e2e overlay's gated admin UI). |
| Prometheus | `OPENCG__PROMETHEUS__HOST_PORT` | 9090 | Web UI and HTTP API, no login. |
| Tempo | `OPENCG__TEMPO__HOST_PORT` | 3200 | Query API, no login. |

Like every other port, they bind to `OPENCG__BIND_ADDRESS` (loopback by default).

### Grafana login

Anonymous access is off, even on loopback. Sign in as `admin` with the password from `OPENCG__GRAFANA__ADMIN_PASSWORD` (default `admin`). Set a real password in `.env` before binding beyond loopback. Grafana stores the password in its volume on first start, so changing it later needs `make down-v` (or a password reset with `grafana cli admin reset-admin-password` inside the container).

### Dashboards

The dashboards are code: JSON in [`infra/grafana/dashboards/`](../infra/grafana/dashboards/), provisioned read-only into the "openCG" folder against the fixed datasource UIDs `opencg-prometheus` and `opencg-tempo`. Edits in the Grafana UI are not saved; to change a dashboard, edit it in Grafana, export the JSON, normalise it (sorted keys, `"id": null`, no `version`) and commit it. `make check-dashboards` (part of `make ci-static`) checks every file: valid JSON, a stable `uid`, only the two datasource UIDs, and only `opencg_*` metrics that `opencg_shared.metrics` defines.

| Dashboard | Shows |
|---|---|
| openCG / Requests | Request volume, outcomes (`ok`, `error`, `rejected`), MCP latency, links to recent traces in Tempo |
| openCG / Pipeline stages | p50/p95/p99 and throughput for every stage (`identity`, `hybrid_retrieval`, `assemble`, `vector_search`, `mcp`, …) |
| openCG / Tokens and cost | Tokens and estimated cost by tenant, provider and model; unpriced tokens |
| openCG / Ingestion | Runs, documents, chunks and duration per connector; ingest embedding tokens; extractor edges and errors |
| openCG / Audit | Retrieval and graph audit writes, failures, and audit coverage of retrievals |
| openCG / Providers | Provider errors by HTTP status or `timeout`, traffic per provider, collector span throughput, scrape targets |

### Finding a trace by correlation ID

Every MCP result and every audit row carries a `correlation_id`. In Grafana, open **Explore → Tempo** and run:

```
{ span.correlation_id = "<correlation id>" }
```

or query Tempo directly: `curl -G http://localhost:3200/api/search --data-urlencode 'q={ span.correlation_id = "<id>" }'`. Traces are searchable a few seconds after the call ends.

### Metric catalogue

| Metric | Labels | Served by |
|---|---|---|
| `opencg_requests_total` | `tool`, `outcome` (`ok`, `error`, `rejected`) | pipeline, MCP server |
| `opencg_stage_latency_seconds` (histogram) | `stage` | pipeline, ingestion, MCP server (`stage="mcp"`) |
| `opencg_tokens_total` | `stage`, `model`, `provider`, `tenant`, `direction` | pipeline, ingestion |
| `opencg_cost_usd_total` | `provider`, `model`, `tenant` | pipeline, ingestion |
| `opencg_cost_unpriced_tokens_total` | `provider`, `model` | pipeline, ingestion |
| `opencg_provider_errors_total` | `provider`, `error_code` | pipeline, ingestion |
| `opencg_audit_writes_total` | `log` (`retrieval`, `graph`), `outcome` | pipeline |
| `opencg_ingestion_runs_total` | `connector`, `status` | ingestion |
| `opencg_ingestion_documents_total`, `opencg_ingestion_chunks_total` | `connector` | ingestion |
| `opencg_ingestion_run_duration_seconds` (histogram) | `connector` | ingestion |
| `opencg_extractor_edges_total`, `opencg_extractor_errors_total` | `relation`, `state` / `reason` | ingestion |

Labels never carry query text, principals, entity IDs or correlation IDs. The `provider` label comes from the `provider` field of the `providers.<role>` block that served the call: `ollama` for the compose-local embeddings, `ollama-cloud` for Ollama Cloud chat. An older config that says `provider: ollama` with an `ollama.com` base URL is relabelled `ollama-cloud` at start-up, with one log line.

**Ingestion multiprocess metrics.** The ingestion server and the CLI runs started with `docker compose exec` (`make ingest-git`, the smoke) share one container. `PROMETHEUS_MULTIPROC_DIR=/run/opencg-metrics` (a tmpfs) makes every process write its counters there, and the server's `/metrics` sums them, so CLI runs are counted after the process exits. The directory is emptied at every container start (a fresh tmpfs, and the compose `command` clears it before starting the server), so counters reset when the container restarts; Prometheus `rate()` and `increase()` handle that. A multiprocess registry only lists families some process has written to, so a family appears after its first event.

### Pricing

Cost is an estimate from the `observability.pricing` table in `opencg.yaml`: USD per 1,000 tokens, one row per `(provider, model)`, each with a required `source` and `as_of`. A missing `source` or `as_of` stops the service from starting.

- Local Ollama (`ollama` / `nomic-embed-text`) is priced at zero.
- Ollama Cloud rows use the per-token rates published at <https://ollama.com/pricing>. The default chat model `gemma3:4b` had no published rate on 2026-11-12, so it is **unpriced** by default.
- A pair with no row is never counted as free: its tokens go to `opencg_cost_unpriced_tokens_total`, its `cost_usd` is `null`, `cost_complete` is `false`, the admin UI shows "unpriced", and each process logs one warning per pair.

To refresh a rate: check the provider's price page, update `input_usd_per_1k` / `output_usd_per_1k` (the page lists USD per million tokens; divide by 1,000), set `source` and `as_of` to today, and restart the pipeline and ingestion (`make up-d`, or `make up-obs` with the overlay). Prices apply from the restart on; counters and audit rows already written keep the old figures.

**Existing databases.** Cost columns on the audit log come from `infra/postgres/init/060_audit_cost.sql`, which Postgres runs only on an empty volume. On an existing volume apply it once (it is idempotent):

```bash
docker compose -f infra/compose/docker-compose.yml --env-file .env exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < infra/postgres/init/060_audit_cost.sql
```

### Retention, disk and RAM

| Backend | Retention | Volume |
|---|---|---|
| Prometheus | `OPENCG__PROMETHEUS__RETENTION` (default `7d`), capped at 2 GB | `prometheus-data` |
| Tempo | 48 h of trace blocks | `tempo-data` |
| Grafana | users and preferences only (dashboards come from files) | `grafana-data` |

The three backends add about 700 MB of resident memory, measured on 2026-11-12 after `make smoke-obs`: Tempo about 340 MB, Grafana about 260 MB and Prometheus about 70 MB. Tempo grows with trace volume and retention. On Docker Desktop, make sure the VM has headroom before `make up-obs`. `make down-v` deletes all three volumes.

### Observability troubleshooting

- **A Prometheus target is down** (Prometheus → Status → Targets, or `curl -s localhost:9090/api/v1/targets`): `pipeline`, `ingestion`, `mcp-server` are scraped on their container ports, `otel-collector` on `:8888`. A down `otel-collector` target usually means the collector was started without the overlay config; run `make up-obs` again. A down app target usually means the service is still starting or restarting (`make ps`).
- **No traces in Tempo**: check that the collector loaded both configs (`docker compose ... logs otel-collector` should show the `otlp/tempo` exporter), that `OTEL_EXPORTER_OTLP_ENDPOINT` is not `none`, and that Tempo is ready (`curl localhost:3200/ready`). Export errors to `tempo:4317` in the collector log mean Tempo is not running. Search results appear a few seconds after a trace ends.
- **Grafana shows "No data"**: the time range may predate the first scrape, or a family has not been written yet (for example `opencg_provider_errors_total` stays empty until a provider call fails).
- **Grafana port clash**: move it with `OPENCG__GRAFANA__HOST_PORT` in `.env`.

## Audit log

Every retrieval writes a row to `opencg.audit_log` (range-partitioned on `created_at`; only the default partition exists until weekly partitions are pre-created; append-only enforced by trigger). The pipeline exposes two read endpoints:

```bash
curl http://localhost:8000/audit/recent?limit=50
curl http://localhost:8000/audit/42
```

The admin UI's `/queries` page consumes these.

## Troubleshooting

### Fresh clone

- **`make up-d` fails with `env file …/.env not found`**: run `cp .env.example .env` first.
- **`Bind for 127.0.0.1:<port> failed: port is already allocated`**: another process or stack owns that port. Move openCG's side with the matching `OPENCG__*__HOST_PORT` in `.env` (see "Network exposure and host ports"), then `make up-d`. `docker ps --format '{{.Names}}\t{{.Ports}}'` shows who holds it.
- **The MCP server or admin UI never becomes healthy**: both wait for the pipeline, which waits for Postgres, Qdrant, Valkey and Ollama. `make ps` shows which dependency is still starting.
- **`make test` can't find `pytest`, or `make lint` can't find `ruff`**: run `make bootstrap`, which installs the root `dev` dependency group (pytest, pytest-asyncio, respx, ruff) from `uv.lock`.
- **`make e2e` says Chromium is missing**: `make bootstrap` installs it, or run `pnpm --filter @opencg/admin-ui exec playwright install chromium`. On Linux add `--with-deps` for the system libraries.
- **Images rebuild slowly or the build context is huge**: the repo-root `.dockerignore` keeps `node_modules`, `.venv` and build output out of the context. If you vendor something large, add it there.

### Running stack

- **`make up-d` hangs on `ollama` health** — first start has to download the embedding model. Tail `docker compose logs ollama` to watch the pull. If it hangs longer than ~5 minutes, check the host's network access to `registry.ollama.ai`.
- **`pipeline /readyz` returns 503** — typically Postgres or Qdrant is still starting; `make ps` shows healthcheck state.
- **Observability overlay problems** — see [Observability troubleshooting](#observability-troubleshooting).
- **Embedding errors after a model swap** — Qdrant collections retain the old vector dimension. Run `make down-v` and re-ingest.
- **`Authorization: Bearer …` showing up in local Ollama logs** — fine. Local Ollama ignores the header. If you don't want it, leave `OPENCG__OLLAMA__API_KEY` unset.
