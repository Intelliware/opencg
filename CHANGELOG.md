# Changelog

All notable changes to openCG are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each entry names the OpenSpec change that carries its full contract; archived changes are in [`openspec/changes/archive/`](./openspec/changes/archive/).

## [Unreleased]

### Breaking

- **Removed the shared-secret stopgaps** (`add-identity-and-opa`): the admin UI password gate (`OPENCG__ADMIN_UI__PASSWORD`, `/login`, `/api/auth/login`, `/api/auth/logout`) and the MCP server's built-in OAuth server (`OPENCG__MCP__OAUTH_PASSWORD`, `/authorize`, `/token`, `/register`, `/revoke`, `/.well-known/oauth-authorization-server`, `POST /oauth/approve`). Services **refuse to start** if either variable is set. See `docs/OPERATIONS.md` "Migrating from the stopgaps".
- `OPENCG__MCP__HTTP_TOKEN` is accepted only when `OPENCG__ENVIRONMENT=dev`. An **unset `OPENCG__ENVIRONMENT` means `production`**; `.env.example` and compose set `dev`.
- `none` auth mode refuses to start when `OPENCG__BIND_ADDRESS` is not a loopback address.
- Retrieval entitlement moved from a role map in the pipeline to OPA. `confidential:<domain>` content now needs the `<domain>` role, and unknown classifications are denied.

### Added

- **Real identity and policy** (`add-identity-and-opa`): `OPENCG__AUTH__MODE=oidc` validates access tokens from any OIDC issuer in every service; the MCP server is an OAuth protected resource; the admin UI signs in with authorization code + PKCE and keeps server-side sessions in Valkey. A bundled Keycloak (`26.8.1`) runs in the same compose project for local use, smoke, e2e and CI.
- OPA (`1.21.4`) decides every retrieval candidate (one batched call, before the token budget) and every API action, in both auth modes, failing closed with `503 policy_unavailable`. Policies, data and tests live in `infra/opa/` (`make opa-test`, `make opa-revision`).
- `opencg.access_audit_log` (append-only) records denials and allowed state-changing actions; retrieval audit rows record `auth_method` and each candidate's policy decision and revision. Apply `070_access_audit.sql` to an existing volume with `make db-apply`.
- Ingestion runs take a `classification` (`--classification` on the CLI); runs record `requested_by`.
- Dev-only named API keys (`make api-key`), `OPENCG__ENVIRONMENT`, and `opencg_auth_failures_total{service,reason}`.
- **Optional observability stack** (`add-observability-stack`): Prometheus `v3.15.1`, Tempo `3.1.1` and Grafana `13.2.5` in a new opt-in compose overlay, `infra/compose/docker-compose.observability.yml`. It is **not** part of the default stack: start it with `make up-obs` (about 700 MB more RAM), stop it with `make down`. Grafana (port 3030, login required, no anonymous access) ships six provisioned dashboards: requests, pipeline stages, tokens and cost, ingestion, audit, and providers. See `docs/OPERATIONS.md` § Observability.
- One connected trace per MCP tool call: the MCP server now exports OpenTelemetry spans (`mcp.<tool>`) and propagates `traceparent` to the pipeline, every span carries `correlation_id`, and each model call has its own `model.embed` / `model.chat` span.
- `/metrics` on the ingestion service (multiprocess, so CLI runs count) and the MCP server, alongside the pipeline. New series for cost, unpriced tokens, audit writes and ingestion runs, documents, chunks and duration; stage latency, provider errors and error outcomes are now recorded.
- Estimated cost: an `observability.pricing` table in `opencg.yaml` (with `source` and `as_of` on every row), `opencg_cost_usd_total`, `by_provider` / `estimated_cost_usd` / `cost_complete` in the usage envelope, cost columns on the retrieval audit row (`infra/postgres/init/060_audit_cost.sql`; apply it by hand on an existing volume), and cost beside every token count in the admin UI. A model with no price shows as "unpriced", never as free.
- `make smoke` now also checks every service's `/metrics`; `make smoke-obs` checks Prometheus targets, token and cost series, the Tempo trace and the Grafana dashboards. `make check-dashboards` lints the dashboard JSON in `make ci-static`.
- CI: a new `observability` job runs `make smoke-obs` on every pull request into `main`, on pushes to `main` and nightly. It is listed as a required check in `.github/rulesets/main-branch-protection.json`.

### Changed

- **Admin UI on Next.js 16.4.5 and React 19** (`upgrade-admin-ui-next-16`). 16.4.5 is taken as a recorded exception to the two-week rule because it is a security release. `middleware.ts` is now `proxy.ts` (Node runtime). Contributors need Node 20.9 or newer.
- New `make hydration-stress` check; CI runs a smaller pass nightly.
- The default chat model (used by knowledge-graph text extraction) is now Ollama Cloud `gemma4:31b` instead of `gemma3:4b`, which has no published per-token price. Set `OPENCG__PROVIDERS__CHAT__MODEL` to keep the old model.
- **Provider label for Ollama Cloud chat is now `ollama-cloud`** (was `ollama`) on tokens, cost, provider errors and spans; `providers.chat.provider` defaults to `ollama-cloud`, and an older `provider: ollama` block with an `ollama.com` base URL is relabelled at start-up. Queries or dashboards that filter chat on `provider="ollama"` need updating.
- Embedding tokens spent during ingestion are now counted (`opencg_tokens_total{stage="ingest_embed"}`).
- `make down` and `make down-v` also remove the observability overlay's containers (and, for `down-v`, its volumes) and orphaned overlay services.

### Fixed

- Intermittent React hydration error #418 in the admin UI under load (#2): 0 in 1,680 stressed loads on Next 16 vs 34 in 560 on 15.5.29. The e2e reload workaround is removed.

## [0.1.0] - 2026-11-10

The first public release.

### Added

- **Retrieval pipeline and MCP server** (`bootstrap-thin-mvp`). A TypeScript MCP server and a Python pipeline: stub identity, hybrid retrieval (Qdrant dense search fused with Postgres full-text search by reciprocal rank fusion), token-budgeted assembly, and an append-only audit log. Embeddings come from a compose-internal Ollama.
- **Git ingestion** (`bootstrap-thin-mvp`, `adopt-graphifyy`). A CLI and HTTP API that clone, chunk, embed and catalogue a repository. graphifyy provides language-aware file discovery and code symbols.
- **Admin UI** (`add-admin-vector-and-content`): vector search, an entity browser with detail, lineage and tombstoning, and ingestion control with a "Run now" form.
- **Knowledge graph** (`add-knowledge-graph`). Named concept relationships on Apache AGE: deterministic code graphs, best-effort text extraction, traversal, candidate review and an editable relationship vocabulary.
- **Graph explorer** (`add-graph-explorer-view`, `default-graph-to-map`, `update-graph-map-detail`). An interactive force-directed map, now the default view of `/graph`, with concept search and a navigable detail panel.
- **Remote MCP** (`add-mcp-http-transport`, `add-mcp-oauth-stopgap`). A Streamable HTTP transport with an optional bearer token, and a minimal OAuth stopgap for claude.ai connectors.
- **Deterministic smoke test** (`stabilize-full-smoke`): a bounded end-to-end check that uses a local fixture, a chat stub and OpenTelemetry verification.
- **Release readiness** (`prepare-open-source-release`):
  - A Playwright end-to-end suite for every admin UI route (`make e2e`).
  - CI with `static`, `dependency-review` and full-stack `stack` jobs, plus Dependabot.
  - `make ci`, an optional admin UI access gate, and validation of submitted ingestion URLs.
  - A main-branch ruleset, and the community files: contributing guide, security policy, code of conduct and third-party notices.

### Changed

- **Admin UI redesign** (`adopt-shadcn-and-tremor`, `reorder-admin-nav`): shadcn/ui and Tremor, light and dark themes, an overview dashboard, and Graph second in the navigation.
- **Project name** (`rename-to-cortex`, `rename-to-open-context-graph`): now **Open Context Graph** (openCG).
- **Safer compose defaults** (`prepare-open-source-release`):
  - Every port binds to `127.0.0.1` and can be moved in `.env`.
  - The Postgres credentials live in `.env`.
  - The MCP host port is 8181, and the container Ollama is published on 11435.
  - Smoke-only services moved into an overlay.
  - Images run as non-root with health checks, and build from the lockfiles.

### Fixed

- Code-graph nodes and symbol IDs use the real repository path instead of a temporary file name, so re-ingesting an unchanged file no longer creates duplicate symbol chunks (`fix-code-graph-filename-leak`).
- Tombstoned entities are no longer returned by retrieval or the admin vector search (`exclude-tombstoned-from-retrieval`).
- A fresh clone now builds, lints, type-checks and tests cleanly (the admin UI image was missing `public/`), and `make lint` no longer depends on a leftover build (`prepare-open-source-release`).
- Admin UI (`prepare-open-source-release`):
  - Concept search on the Concepts tab no longer jumps to the Map tab.
  - Entity detail pages no longer raise a hydration error outside UTC.
  - Sidebar links clicked just after opening the graph are no longer cancelled.

### Security

- Dependencies upgraded to clear every critical and high advisory; the remaining moderate and low ones are listed in [`SECURITY.md`](./SECURITY.md).
- "Run now" ingestion refuses option injection, `ext::` and `file://` transports, embedded credentials, and hosts that resolve to private addresses.
- A root `.dockerignore` keeps `.env` and local build state out of image build contexts.

[Unreleased]: https://github.com/Intelliware/opencg/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Intelliware/opencg/releases/tag/v0.1.0
