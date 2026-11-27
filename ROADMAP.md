# Roadmap

What openCG plans to build, and what to pick up next. Shipped work is recorded in [`CHANGELOG.md`](./CHANGELOG.md), the README's shipped-changes table and [`openspec/changes/archive/`](./openspec/changes/archive/); this file lists only work still to do.

## How to use this roadmap

- **Pick an item** with status `ready`, preferably from **Now**. Check its `Depends on`.
- **Start it:** run `openspec new change <id>` (the item's heading is the change name), write the proposal, and in the same pull request set the item to `proposed` and add `Owner`.
- **Build it:** once the owner approves the proposal, set the item to `in-progress`.
- **Finish it:** the pull request that runs `openspec archive <id>` deletes the item from this file.
- **Drop or split it:** delete or replace the item and give the reason in the pull request. To abandon a started change, delete its `openspec/changes/<id>/` folder and set the item back to `ready`.
- **Add an item:** open a pull request that adds it to the right band. Ideas from outside start as a [feature proposal issue](https://github.com/Intelliware/opencg/issues/new?template=feature_proposal.yml).
- `make check-roadmap` (part of `make ci-static`) keeps this file and `openspec/changes/` in step. See [CONTRIBUTING](./CONTRIBUTING.md#picking-up-work).

Each item has:
- a heading, which is its kebab-case ID and its OpenSpec change name;
- `Status`: `ready`, `proposed` or `in-progress`;
- `Size`: `S` about a day, `M` under a week, `L` larger (split it first);
- `Capabilities` (from `openspec/specs/`, or `new: <name>`), `Depends on`, and `Source`;
- optionally `Owner` and `Issue`;
- a **Problem** and a **Scope**.

## Now

### add-identity-and-opa

- **Status:** in-progress
- **Size:** L
- **Capabilities:** new: identity-access, entitlement-audit, mcp-server, admin-ui, retrieval-pipeline
- **Depends on:** none
- **Source:** add-foundation 2.6, 4.3, 5.2, 5.7, 12.1

**Problem:** shipped to `main` in PR #4; the change is not archived yet.

**Scope:** archive it. Its deferred follow-ups are the `split-keycloak-env`, `restrict-dynamic-client-registration` and `add-graph-entitlement` items.

### add-observability-stack

- **Status:** in-progress
- **Size:** L
- **Capabilities:** new: observability, retrieval-pipeline, mcp-server, ingestion, admin-ui
- **Depends on:** none
- **Source:** add-foundation 13.2–13.6

**Problem:** shipped to `main` in PR #4; the change is not archived yet.

**Scope:** archive it, after its remaining owner step: apply the `observability` required check to the live ruleset. Its deferred follow-ups are the `add-log-aggregation` and `add-observability-negative-checks` items.

### upgrade-admin-ui-next-16

- **Status:** in-progress
- **Size:** M
- **Capabilities:** admin-ui
- **Depends on:** none
- **Source:** issue #2

**Problem:** shipped to `main` in PR #4; the change is not archived yet.

**Scope:** post the issue #2 closing summary, then archive it.

### add-graph-entitlement

- **Status:** ready
- **Size:** M
- **Capabilities:** knowledge-graph, entitlement-audit
- **Depends on:** none
- **Source:** add-identity-and-opa task 15.10

**Problem:** `/graph/*` applies no entitlement. Any caller with `graph.read` (the `reader` role) sees concepts, model-written descriptions and relationships extracted from confidential entities, and the IDs of those entities.

**Scope:** filter concepts, edges, neighbours and traversal results by the entitlement of their source and evidence entities, through the same OPA `entitle` decision the entity routes use. Decide how a concept with mixed sources is shown. Cover it in smoke and e2e for each role.

### restrict-dynamic-client-registration

- **Status:** ready
- **Size:** S
- **Capabilities:** identity-access
- **Depends on:** none
- **Source:** add-identity-and-opa task 15.9

**Problem:** the bundled Keycloak allows anonymous dynamic client registration in every environment, so anyone who can reach it can register an OAuth client.

**Scope:** turn anonymous registration off in staging and production, or cap it with trusted hosts and a client limit. Document how operators register MCP clients instead.

### add-showcase-seed-packs

- **Status:** ready
- **Size:** L
- **Capabilities:** new: showcase-packs, ingestion, smoke-testing
- **Depends on:** none
- **Source:** owner request (2026-11-12, restated 2026-11-27)

**Problem:** the only seeded data is the smoke fixture, so there is no realistic way to demonstrate openCG's access control, knowledge graph and cost tracing to financial-services audiences.

**Scope:**
- Three fully synthetic packs: wealth, payments and retail banking. Use fictional institutions and people only.
- Policies, procedures, product sheets and runbooks, split across `public`, `internal` and `confidential:<domain>` sources. Ingestion sets classification per run and accepts only `https`, `ssh` or `git` repository URLs.
- Demo personas and roles in the bundled Keycloak.
- `make demo-seed PACK=…` and `make demo-reset`.
- `docs/DEMO.md`: run the stack, connect Claude Code, Claude Desktop and Cursor over MCP, and follow a per-pack script.
- Smoke coverage that each pack ingests and that persona differences hold.

## Next

### add-answerability-check

- **Status:** ready
- **Size:** M
- **Capabilities:** retrieval-pipeline, mcp-server
- **Depends on:** none
- **Source:** auto-ontology evaluation (2026-11-27)

**Problem:** retrieval always returns its best fragments, even when nothing in the catalogue covers the question, so agents answer from weak context instead of saying they can't.

**Scope:** a coverage signal on `retrieve_for_context` (and possibly a separate `check_answerable` tool) that reports which parts of the question have support and how strong it is. The signal comes from retrieval scores and graph matches, with no extra model call by default.

### add-ossie-import

- **Status:** ready
- **Size:** M
- **Capabilities:** knowledge-graph
- **Depends on:** none
- **Source:** auto-ontology evaluation (2026-11-27)

**Problem:** organisations that already model business terms (for example with NVIDIA auto-ontology) have to re-derive them from documents, and the two graphs drift.

**Scope:** import Apache Ossie semantic-model YAML as confirmed concepts and relationships, with their source recorded. Re-importing is idempotent. Export can follow later.

### add-structured-data-routing

- **Status:** ready
- **Size:** M
- **Capabilities:** mcp-server, retrieval-pipeline
- **Depends on:** add-answerability-check
- **Source:** auto-ontology evaluation (2026-11-27)

**Problem:** openCG covers documents and code; questions about numbers in databases need a text-to-SQL layer such as auto-ontology, and agents must pick the right server themselves.

**Scope:** configure an external MCP server for structured data. Return a routing hint, or forward the question, when coverage shows a data question. Identity is propagated; nothing is forwarded without configuration.

### add-confluence-connector

- **Status:** ready
- **Size:** L
- **Capabilities:** ingestion
- **Depends on:** none
- **Source:** add-foundation 10.1, 10.3, 10.7; deferred reason in `services/ingestion`

**Problem:** most enterprise knowledge lives in Confluence, and git is the only connector.

**Scope:**
- The connector framework from the vision: `discover`, `fetch`, `list_changes`, `chunk`, `metadata`, scheduling with retry and backoff.
- A Confluence connector with incremental sync, storage-format-to-text conversion and per-space classification.
- Fixture tests.

### add-rerank-and-compression

- **Status:** ready
- **Size:** M
- **Capabilities:** retrieval-pipeline, model-providers
- **Depends on:** none
- **Source:** add-foundation 5.6

**Problem:** retrieval skips pipeline stage 5. Fused results go straight to assembly, which only trims to the token budget.

**Scope:** a cross-encoder rerank through a provider adapter, plus token-budget-aware compression that drops whole documents first. Both report per-stage tokens and cost.

### split-keycloak-env

- **Status:** ready
- **Size:** S
- **Capabilities:** identity-access
- **Depends on:** none
- **Source:** add-identity-and-opa task 15.8

**Problem:** Keycloak's admin and database secrets sit in the shared `.env` that every service loads.

**Scope:** move them into their own env file that only the Keycloak service reads. Update `.env.example`, OPERATIONS and the dev-only guards.

### add-log-aggregation

- **Status:** ready
- **Size:** M
- **Capabilities:** observability
- **Depends on:** none
- **Source:** add-observability-stack task 9.4a; add-foundation 13.1

**Problem:** traces and metrics are in the overlay, but logs are not, so there is no jump from a trace to its log lines.

**Scope:** structured JSON logs with `trace_id` and `correlation_id` from every service, Loki in the observability overlay, and trace-to-logs links in Grafana.

### isolate-smoke-fixtures

- **Status:** ready
- **Size:** S
- **Capabilities:** smoke-testing
- **Depends on:** none
- **Source:** add-identity-and-opa verification (2026-11-23)

**Problem:** leftover smoke fixtures with identical text can push the current run's documents out of the top results, so smoke fails intermittently on long-lived stacks.

**Scope:** use run-unique query text and content, and clean up fixtures from earlier runs at the start of a run.

## Later

### add-intent-classifier

- **Status:** ready
- **Size:** M
- **Capabilities:** retrieval-pipeline, model-providers
- **Depends on:** none
- **Source:** add-foundation 5.3

**Problem:** pipeline stage 2 is skipped, so every query gets the same retrieval plan.

**Scope:** classify intent through a provider adapter into a `RetrievalPlan` (sources, weights, graph depth), with skip rules, token accounting and the plan recorded in the audit row.

### add-graph-enriched-retrieval

- **Status:** ready
- **Size:** M
- **Capabilities:** retrieval-pipeline, knowledge-graph
- **Depends on:** add-graph-entitlement
- **Source:** add-foundation 5.5

**Problem:** retrieval does not use the knowledge graph, so related concepts never reach the agent unless their text matches.

**Scope:** enrich candidates with catalogue metadata and one hop of confirmed graph context, within the token budget and subject to entitlement.

### add-custom-api-connector

- **Status:** ready
- **Size:** M
- **Capabilities:** ingestion
- **Depends on:** add-confluence-connector
- **Source:** add-foundation 10.4

**Problem:** internal systems that expose JSON APIs can't be ingested.

**Scope:** a YAML-configured HTTP connector with JSONPath extraction and field mapping, built on the connector framework.

### add-web-indexer

- **Status:** ready
- **Size:** M
- **Capabilities:** ingestion
- **Depends on:** add-confluence-connector
- **Source:** add-foundation 10.5

**Problem:** public and intranet web pages can't be ingested.

**Scope:** an allow-listed crawler that respects robots.txt and nofollow, resolves canonical URLs and skips binaries.

### add-background-enrichment

- **Status:** ready
- **Size:** L
- **Capabilities:** new: background-enrichment, catalog-store, knowledge-graph
- **Depends on:** none
- **Source:** add-foundation 8.3, 11.1–11.4, 11.6

**Problem:** nothing happens after ingest: freshness is never updated and relationships are only extracted once.

**Scope:** a worker runtime on Valkey, a change-driven worker on ingest events, a freshness sweep that drives `freshness_state`, and scheduled relationship inference.

### add-usage-feedback

- **Status:** ready
- **Size:** M
- **Capabilities:** mcp-server, catalog-store
- **Depends on:** add-background-enrichment
- **Source:** add-foundation 2.2 (usage signals), 4.6, 11.5

**Problem:** the `submit_feedback` MCP tool is advertised but returns "not implemented", so the system can't learn from use.

**Scope:** store feedback as usage signals, aggregate a usage score, and make it available to ranking.

### add-audit-replay

- **Status:** ready
- **Size:** M
- **Capabilities:** entitlement-audit, vector-index
- **Depends on:** none
- **Source:** add-foundation 5.10, 9.4, 12.4, 12.6

**Problem:** audit rows record what was returned, but a decision can't be reconstructed: `vector_snapshot_id` is always null and there is no replay.

**Scope:** record vector snapshots per request, and add a replay endpoint that rebuilds the context from stored versions and reports any divergence.

### add-audit-search

- **Status:** ready
- **Size:** S
- **Capabilities:** entitlement-audit, admin-ui
- **Depends on:** none
- **Source:** add-foundation 12.3, 12.5

**Problem:** the audit API offers only recent rows and lookup by ID. The `legal_hold` flag exists in the schema, but nothing can set it.

**Scope:** filter by correlation ID, principal, time, entity and tool, and add an admin action to set legal hold.

### add-audit-partitions

- **Status:** ready
- **Size:** S
- **Capabilities:** entitlement-audit
- **Depends on:** none
- **Source:** add-foundation 2.2; README known issue

**Problem:** every audit row lands in the default partition.

**Scope:** pre-create weekly partitions on a schedule and document retention.

### add-graph-communities

- **Status:** ready
- **Size:** M
- **Capabilities:** knowledge-graph, admin-ui
- **Depends on:** none
- **Source:** add-foundation 7.5

**Problem:** the graph has no higher-level structure for browsing or summarising.

**Scope:** a scheduled community-detection job over confirmed edges, with stored assignments shown in the graph map.

### add-vector-projection

- **Status:** ready
- **Size:** M
- **Capabilities:** admin-ui, vector-index
- **Depends on:** none
- **Source:** add-foundation 14.4

**Problem:** vector neighbourhoods are shown only as ranked lists.

**Scope:** a 2D projection (for example UMAP) of a neighbourhood in `/vectors`, computed by a small sidecar.

### add-provider-adapters

- **Status:** ready
- **Size:** M
- **Capabilities:** model-providers
- **Depends on:** none
- **Source:** add-foundation 6.1, 6.3–6.5, 6.7

**Problem:** only Ollama (local and Cloud) adapters exist.

**Scope:** provider protocols, a registry resolving `provider:model`, Anthropic and OpenAI-compatible adapters with usage accounting, and recorded-response tests.

### add-local-prod-profile

- **Status:** ready
- **Size:** M
- **Capabilities:** new: deployment
- **Depends on:** none
- **Source:** add-foundation 15.2, 15.3

**Problem:** compose has a single `dev` profile with built images and no hot reload, and there is no production-shaped local profile.

**Scope:** a source-mounted `dev` profile with hot reload, and a `local-prod` profile with built images, restricted ports and production guards on.

### add-helm-chart

- **Status:** ready
- **Size:** L
- **Capabilities:** new: deployment
- **Depends on:** add-local-prod-profile
- **Source:** auto-ontology evaluation (2026-11-27)

**Problem:** openCG runs only under Docker Compose.

**Scope:** a Helm chart for Kubernetes with external Postgres, Qdrant, Valkey and OIDC, published from CI.

### add-alerting

- **Status:** ready
- **Size:** M
- **Capabilities:** observability
- **Depends on:** add-log-aggregation
- **Source:** add-observability-stack non-goals; README "Not in v0"

**Problem:** dashboards exist but nothing alerts on errors, latency or cost.

**Scope:** Prometheus alert rules and Grafana contact points in the overlay for provider errors, policy-unavailable responses, latency and daily cost.

### add-observability-negative-checks

- **Status:** ready
- **Size:** S
- **Capabilities:** observability, smoke-testing
- **Depends on:** none
- **Source:** add-observability-stack task 7.3

**Problem:** the overlay smoke checks were never shown to fail on a broken config.

**Scope:** scripted runs that break the config deliberately (Tempo exporter removed, ingestion `/metrics` unmounted) and confirm smoke goes red, then green.

### add-durable-ingestion-runs

- **Status:** ready
- **Size:** S
- **Capabilities:** ingestion, admin-ui
- **Depends on:** none
- **Source:** `services/ingestion/src/opencg_ingestion/runs.py`; admin UI ingestion page

**Problem:** ingestion run history is kept in memory and lost on restart.

**Scope:** store runs in Postgres and show their history in `/ingestion`.

### add-multi-tenancy

- **Status:** ready
- **Size:** L
- **Capabilities:** identity-access, catalog-store, vector-index, entitlement-audit
- **Depends on:** add-graph-entitlement
- **Source:** README "Not in v0"

**Problem:** a tenant comes from the token, but data is not fully isolated per tenant across every store and route.

**Scope:** tenant isolation in Postgres, Qdrant and the graph on every route, tenant administration, and tests proving that no data crosses tenants.

### add-contributor-guides

- **Status:** ready
- **Size:** S
- **Capabilities:** new: documentation
- **Depends on:** none
- **Source:** add-foundation 16.2–16.4, 16.6

**Problem:** there is no architecture narrative and no guide for adding a connector or a model provider.

**Scope:** `docs/ARCHITECTURE.md` with the reference architecture diagram, `docs/CONNECTORS.md` and `docs/MODEL_PROVIDERS.md`.
