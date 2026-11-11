# Changelog

All notable changes to openCG are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each entry names the OpenSpec change that carries its full contract; archived changes are in [`openspec/changes/archive/`](./openspec/changes/archive/).

## [Unreleased]

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
