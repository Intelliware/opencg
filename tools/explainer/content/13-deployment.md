---
id: deployment
title: Deployment and Quality
capabilities: deployment, smoke-testing, project-conventions
status: partial
services: postgres, qdrant, valkey, ollama, otel-collector, pipeline, ingestion, mcp-server, admin-ui
stores: postgres, qdrant, valkey
tagline: Ten containers, one command, and a smoke test that proves the whole chain works.
---

## What it is

The Docker Compose stack that runs everything, plus the testing and process
discipline that keeps it honest. `make up-d` builds and starts ten services;
`bash tests/smoke/run.sh` proves that content can go in one end and come out the
other.

## Why it exists

openCG's promise is *self-hostable*. That only means something if a single
command brings up a working stack on a laptop with no cloud account. And a
pipeline with this many moving parts needs an end-to-end test, because every
component can pass its unit tests while the chain between them is broken.

## Flow

### 1. Build and start the stack
`make up-d` runs Docker Compose with the `dev` profile: Postgres, Qdrant, Valkey,
Ollama, the OTel collector, then the pipeline, ingestion, MCP server, and admin
UI. Every host port is written as `${OPENCG__SERVICE__HOST_PORT:-default}` so a
collision can be dodged from `.env` without editing the compose file.
file: infra/compose/docker-compose.yml

### 2. Initialise the database in order
Postgres runs its init SQL in numeric order: `010_extensions` (AGE, pg_trgm,
unaccent, uuid-ossp), `020_catalog`, `030_audit`, `040_graph`,
`050_graph_audit`, `090_grants`. The files start at `010_` specifically so
Apache AGE's own bundled `00-create-extension-age.sql` runs first.
file: infra/postgres/init/010_extensions.sql

### 3. Pull the embedding model on first start
The Ollama container's entrypoint pulls the configured embedding model before
reporting healthy, so the first ingest does not fail on a cold model cache.
file: infra/ollama/entrypoint.sh

### 4. Gate startup on real readiness
Dependent services wait on healthchecks, not just container start. The pipeline
waits for Postgres, Qdrant, Valkey, Ollama, and the collector; the MCP server and
admin UI wait for the pipeline. Each service's `/readyz` probes its actual
dependencies rather than returning a static OK.
file: infra/compose/docker-compose.yml

### 5. Prove the chain end to end
The smoke test ingests a deterministic fixture, retrieves against it, and
asserts the whole path — including a stubbed chat service so graph extraction is
reproducible instead of depending on a live model. It is bounded and isolated so
it can run repeatedly.
file: tests/smoke/run.sh

### 6. Keep the spec ahead of the code
Every feature goes through the OpenSpec workflow before implementation: propose,
design, write testable WHEN/THEN scenarios, validate `--strict`, get approval,
then build. This explainer's per-pillar history is generated from those documents.
file: AGENTS.md

## Facts
- **10 services**, all under the `dev` profile
- Postgres 16 + Apache AGE (`apache/age:release_PG16_1.6.0`), Qdrant v1.12.4, Valkey 8.0, Ollama 0.30.7
- Ports: admin UI 3000, pipeline 8000, ingestion 8100, MCP 8181 on host, Postgres 5432, Qdrant 6333/6334, Ollama 11434
- Volumes: `postgres-data`, `qdrant-data`, `valkey-data`, `ollama-data`
- Tests: `pytest` for Python, `vitest` for TypeScript, one end-to-end smoke script
- Agent guidance is duplicated across `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/opencg.mdc` and must stay in sync

## Gaps
- **No `local-prod` profile.** Only the `dev` profile exists; production packaging is deferred.
- **Valkey runs but is unused.** It is configured and healthy, and nothing connects to it. It is reserved for future caching and job queues.
- **No CI pipeline.** Tests and the smoke script are run by hand.
- **No migration tooling.** Schema changes are init-time SQL, so evolving an existing database means writing the migration yourself.
- **Secrets live in a gitignored `.env`** with no secret manager integration.
