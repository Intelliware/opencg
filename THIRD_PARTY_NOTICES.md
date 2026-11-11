# Third-party notices

openCG's own code is MIT-licensed (see [`LICENSE`](./LICENSE)). It runs alongside, and is built from, third-party software under its own licences. None of it is vendored into this repository: container images are pulled and packages are installed from the lockfiles at build time. All the licences below are compatible with distributing openCG under MIT.

## Services the compose stack runs

| Component | Image | Licence |
|---|---|---|
| PostgreSQL 16 + [Apache AGE](https://github.com/apache/age) | `apache/age:release_PG16_1.6.0` (base of `opencg/postgres-age`) | PostgreSQL Licence; AGE: Apache-2.0 |
| [Qdrant](https://github.com/qdrant/qdrant) | `qdrant/qdrant:v1.12.4` | Apache-2.0 |
| [Valkey](https://github.com/valkey-io/valkey) | `valkey/valkey:8.0-alpine` | BSD-3-Clause |
| [Ollama](https://github.com/ollama/ollama) | `ollama/ollama:0.30.7` | MIT |
| [OpenTelemetry Collector Contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) | `otel/opentelemetry-collector-contrib:0.123.0` | Apache-2.0 |
| Node.js, on Alpine Linux | `node:22-alpine` (base of the admin UI and MCP server images) | Node.js: MIT; Alpine packages: their own licences |
| Python | `python:3.12-slim` (base of the pipeline and ingestion images, and the smoke chat stub) | PSF-2.0; Debian packages: their own licences |

The default embedding model, [`nomic-embed-text`](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5), is downloaded by the Ollama container on first start and is licensed Apache-2.0.

## Notable libraries

- **[graphifyy](https://github.com/safishamsi/graphify)** (MIT): AST-level file discovery and symbol extraction for code ingestion.
- **[Next.js](https://github.com/vercel/next.js)** (MIT), **[React](https://github.com/facebook/react)** (MIT), **[Tremor](https://github.com/tremorlabs/tremor)** (Apache-2.0) and **[shadcn/ui](https://github.com/shadcn-ui/ui)** components (MIT) for the admin UI.
- **[MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)** (MIT) for the MCP server.
- **[FastAPI](https://github.com/fastapi/fastapi)** (MIT), **[asyncpg](https://github.com/MagicStack/asyncpg)** (Apache-2.0), **[httpx](https://github.com/encode/httpx)** (BSD-3-Clause) and **[qdrant-client](https://github.com/qdrant/qdrant-client)** (Apache-2.0) for the Python services.

## Weak-copyleft dependencies

A licence scan of the installed npm and Python dependencies (2026-11-10) found no GPL or AGPL packages. These weak-copyleft packages are used unmodified, which their licences allow:

| Package | Licence | Where |
|---|---|---|
| `@img/sharp-libvips-*` | LGPL-3.0-or-later | Native image library loaded by `sharp`, which Next.js uses for image optimisation. It is dynamically linked and shipped unmodified in the admin UI image; its source is at [lovell/sharp-libvips](https://github.com/lovell/sharp-libvips). |
| `axe-core` | MPL-2.0 | Accessibility checks in the admin UI's development tooling; not shipped. |
| `certifi` | MPL-2.0 | Mozilla's CA certificate bundle for Python TLS clients. |

To repeat the scan: `pnpm licenses list`, and the `License` metadata of each package in `.venv` (`importlib.metadata`).
