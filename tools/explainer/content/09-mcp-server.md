---
id: mcp-server
title: MCP Server
capabilities: mcp-server
status: partial
services: mcp-server
tagline: The standard plug that lets Cursor or Claude call into openCG.
---

## What it is

A small TypeScript service that speaks **Model Context Protocol**, the standard
that lets AI tools discover and call external capabilities. It is the reason
openCG is useful from inside an editor rather than only from a browser.

It is a thin adapter by design: it validates arguments, forwards to the pipeline
over HTTP, and formats the reply. No retrieval logic lives here.

## Why it exists

Without MCP, every AI tool would need a bespoke integration. With it, one server
makes the whole knowledge catalogue available to Cursor, Claude Desktop, Claude
Code, and anything else that speaks the protocol.

## Flow

### 1. Advertise the tool list
Five tools are declared with JSON schemas. Two are real:
`opencg/retrieve_for_context` and `opencg/traverse_graph`. Three
(`search`, `get_entity`, `submit_feedback`) are advertised but return
`not_implemented_in_mvp`, so clients can see the intended surface.
file: services/mcp-server/src/tools.ts

### 2. Accept a call over stdio or HTTP
Both transports run in the same process. **stdio** serves clients that launch
the server as a subprocess, typically `docker run -i`. **Streamable HTTP** serves
clients that connect by URL at `ALL /mcp`, with stateful sessions keyed on an
`mcp-session-id` header.
file: services/mcp-server/src/index.ts

### 3. Authenticate, if configured
If `OPENCG__MCP__HTTP_TOKEN` is set, `/mcp` requires a matching bearer token. If
`OPENCG__MCP__OAUTH_PASSWORD` is set, an OAuth 2.1 router is mounted so
claude.ai can connect as a custom connector. With neither set the endpoint is
open and the server logs a warning.
file: services/mcp-server/src/oauth.ts

### 4. Build the pipeline request
For retrieval, the server mints a correlation id, attaches identity from its own
configuration, sets `tool: "retrieve_for_context"`, and `POST`s to the pipeline's
`/retrieve` with an `x-correlation-id` header so the two services' logs line up.
file: services/mcp-server/src/pipeline-client.ts

### 5. Return JSON as a text block
MCP results come back as a single text content block containing pretty-printed
JSON. Errors return `isError: true` with a `{code, message}` payload — for
example `concept_not_found` when traversal is given a bad concept id.
file: services/mcp-server/src/server.ts

## Facts
- **2 of 5** advertised tools are functional
- `retrieve_for_context`: `query`, `top_k` (1–200, default 20), `token_budget` (min 100, default 4000), `filters`
- `traverse_graph`: `concept_id`, `types`, `depth` (1–4, default 2), `limit` (1–200, default 50), `include_candidates` (default false)
- Listens on **8080** in-container, usually mapped to host **8181** (8080 collides on the dev machine)
- Health: `GET /healthz`, `GET /readyz` (probes the pipeline)
- Connect via stdio `docker run`, direct HTTP URL, or OAuth for claude.ai

## Gaps
- **Three stub tools.** `search`, `get_entity`, and `submit_feedback` are advertised but unimplemented, so `submit_feedback` in particular means no feedback loop exists.
- **`/healthz` and `/readyz` are unauthenticated** even when a bearer token is configured.
- **OAuth is explicitly a stopgap**, not a full authorisation-server implementation.
- **Identity is server-side configuration**, not per-caller. Every request from a given server instance carries the same principal, so multi-user attribution is impossible today.
