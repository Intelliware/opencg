# Open Context Graph — Project Context

Open Context Graph (openCG) is an open-source, self-hostable implementation of an enterprise context-engineering pipeline. It exposes a private knowledge catalogue to any AI tool through MCP, learns continuously from usage, and lets humans review and edit the catalogue (vector neighbourhoods and a named-relationship graph) through an admin UI.

## Vision

> "If your AI architecture is just your LLM tool RAG-ing against a vector database, you don't have an AI architecture. You have one component."

openCG builds out the missing components: identity, intent, hybrid retrieval, catalog/graph enrichment, rerank + compression, entitlement, audit, continuous enrichment, and an inspection UI. Every stage is independently testable, observable, and replaceable.

## Reference architecture

See `docs/reference-architecture/` and `openspec/changes/archive/2026-11-27-add-foundation/design.md` for the diagram and the implementation decisions.

## Stack

| Concern | Choice |
|---|---|
| MCP server | TypeScript (`@modelcontextprotocol/sdk`) |
| Retrieval pipeline + workers + ingestion | Python (FastAPI, arq) |
| Vector store | Qdrant (hybrid dense + sparse) |
| Catalog + graph + audit | Postgres 16 + Apache AGE, `pg_trgm`, `tsvector` |
| Cache / session / streams | Valkey |
| Policy engine | Open Policy Agent (OPA) |
| Default models | Ollama (`nomic-embed-text`, `bge-reranker-v2-m3`, `qwen2.5:*`) and Anthropic Haiku |
| Observability | OpenTelemetry → Tempo / Loki / Prometheus / Grafana |
| Admin UI | Next.js (App Router) |
| Deployment | Docker Compose (`dev` and `local-prod` profiles) |

## Tenancy and auth

- **Single-tenant per deploy** in v0. The data model carries a `tenant` slug to keep the door open for later multi-tenancy.
- **Identity is stubbed** in v0. The propagation contract is set; real auth replaces only the verifier.

## Conventions

- One capability spec per service-shaped concern in `openspec/specs/<capability>/spec.md`. Cross-cutting concerns (observability, deployment, model-providers) also get capability specs.
- Every change starts as a proposal under `openspec/changes/<change-name>/` and is validated with `openspec validate <change-name> --strict` before implementation.
- Per-stage OTel spans are the load-bearing observability primitive. Token accounting lives on those spans.
- Audit records are append-only. Anything that wants to change after the fact gets its own state-transition row, not an UPDATE.
- Open-source first. Hosted models live behind the same adapter interface as local ones.
