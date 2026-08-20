---
id: admin-ui
title: Admin UI
capabilities: admin-ui
status: shipped
services: admin-ui
tagline: Seven pages, one per layer, so nothing in the system is a black box.
---

## What it is

A Next.js 15 application that puts a window on every layer of the stack: what was
ingested, what got vectorised, what the graph believes, and what was handed to a
model. Each page is a lens on a different pillar.

## Why it exists

A retrieval pipeline that cannot be inspected cannot be debugged or trusted. If
a search returns nonsense you need to see whether the chunk was bad, the
embedding was bad, or the ranking was bad — and those are three different pages.

The graph review workflow also makes this load-bearing rather than optional: LLM
candidate edges only become confirmed because a human clicked promote here.

## Flow

### 1. Overview — is anything alive
Stat cards for recent queries, entities, candidate edges, and connectors, plus a
queries-per-day bar chart and top sources.
file: services/admin-ui/src/app/page.tsx

### 2. Graph — explore and review
Four tabs. **Map** (the default) is a force-directed graph you can traverse by
clicking nodes, with adjustable depth. **Concepts** is a searchable list.
**Candidate review** is the promote/demote queue ordered by confidence.
**Vocabulary** manages relationship types.
file: services/admin-ui/src/app/graph/page.tsx

### 3. Vectors — is the embedding layer sane
Type a query, see the raw vector hits with scores and snippets. Reads tenant,
embedding model, and dimensions live from the pipeline's `/readyz`. "Show
neighbours" re-searches from a snippet to explore the local neighbourhood.
file: services/admin-ui/src/app/vectors/VectorExplorer.tsx

### 4. Entities — browse the catalog
A paginated list filterable by source, classification, and freshness. The detail
page shows full body text, metadata, parent/child lineage, which past queries
used the entity, and a tombstone button.
file: services/admin-ui/src/app/entities/page.tsx

### 5. Queries — read the audit trail
Every audited retrieval with principal, tool, query, tokens, latency, and
outcome. Clicking through shows the full record: correlation id, every candidate
considered, and the final set that was returned.
file: services/admin-ui/src/app/queries/page.tsx

### 6. Ingestion — put content in
Connector status cards, a "Run now" box that takes a repo URL, and the recent
run history with document and chunk counts.
file: services/admin-ui/src/app/ingestion/page.tsx

### 7. Reach the pipeline safely
Server components call the pipeline directly over the internal Docker network.
Client components cannot — the browser has no route to `pipeline:8000` — so they
go through thin Next route handlers under `/api/proxy/...` that forward
server-side.
file: services/admin-ui/src/app/api/proxy/graph/[...path]/route.ts

## Facts
- **Next.js 15** App Router, 7 routes plus 4 graph tabs
- Nav order: Overview, Graph, Vectors, Entities, Queries, Ingestion
- Graph map uses `react-force-graph-2d`
- Storybook via **`@storybook/react-vite`** — `@storybook/nextjs` is incompatible with Next 15.5
- Every shared component in `src/components/` must have a `*.stories.tsx` neighbour
- Four proxy routes; `graph` is a catch-all forwarder
- All fetches use `cache: "no-store"` so views are never stale

## Gaps
- **No authentication.** Anyone who can reach port 3000 can tombstone entities and rewrite the graph.
- **The shadcn/Tremor redesign never landed** — that change sits at 0 of 26 tasks, so the UI is functional rather than polished.
- **Tombstoned entities still appear** in the entity list because the query has no filter for them.
- **Ingestion run history is in-memory**, so the page goes blank after a container restart.
- **No editing of catalog content** — you can tombstone an entity but not correct it.
