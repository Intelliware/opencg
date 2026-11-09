## Context

The repo is public, but it has only been run on the maintainer's machine, where cached images, a populated `node_modules` and globally installed tools hide gaps. The review that motivates this change ran `pnpm install --frozen-lockfile`, `uv sync --all-packages`, `pnpm -r build`, `pnpm -r test`, the pytest suites, `pnpm -r lint`, `ruff` and `pnpm build-storybook` from the committed tree. 

Baseline results (2026-11-09), re-run on a fresh `git clone` of `39652e2` with Docker (task 1.1–1.4). The stack ran as compose project `opencg-fresh` so the maintainer's volumes were untouched:

| Check | Result |
|---|---|
| `pnpm install --frozen-lockfile`, `uv sync` | pass |
| `make test-mcp` (23) / `make test-ui` (54) | pass |
| `make test-pipeline` / `make test-ingestion` | **fail**: `Failed to spawn: pytest` (test extras not installed by `uv sync`) |
| `make lint` | **fail**: `next lint` has no config and prompts interactively; `ruff` is not installed (85 errors via `uvx`) |
| `tsc --noEmit` (admin-ui) | **fail**: jest-dom matcher types |
| `pnpm build-storybook` | **fail**: `no such directory: …/admin-ui/public` |
| Image builds: postgres, pipeline, ingestion, mcp-server | pass |
| Image build: admin-ui | **fail**: `"/app/services/admin-ui/public": not found`, which makes `make up-d` fail outright |
| `make up-d` with the default `.env` (after a local `public/` workaround) | **fail**: `Bind for 0.0.0.0:8080 failed: port is already allocated` (MCP default 8080; README documents 8181) |
| Stack with `OPENCG__MCP__HOST_PORT=8181` | all 10 services healthy in ~45 s, including the first pull of `nomic-embed-text` |
| `bash tests/smoke/run.sh` | pass in 3 s (2 parents, 3 chunks, stub mode, OTel spans verified) |
| Admin UI routes `/`, `/queries`, `/vectors`, `/entities`, `/entities/[id]`, `/ingestion`, `/graph` (HTTP status only) | 200; vector-search proxy returns current-run hits |
| `gitleaks detect` (v8.21.2, full history, 39 commits) | no leaks found |

Also observed: compose publishes Ollama on `0.0.0.0:11434`, and a native host Ollama on `127.0.0.1:11434` binds alongside it without error, so `localhost:11434` silently becomes ambiguous. Loopback binds and a configurable host port (task 3.1) remove this.

## Goals / Non-Goals

**Goals**

- A newcomer gets from `git clone` to a green `make ci` with only Docker, Node 20+, pnpm and uv installed.
- Every admin UI page has a browser-level test that runs against real services.
- CI catches each class of breakage found above before it reaches `main`.
- Nothing in the default configuration exposes data stores or destructive admin actions beyond loopback.

**Non-Goals**

- Real identity and authorization (OPA, IdP-backed OAuth). That remains in `add-foundation`. The admin access gate here is a shared-secret stopgap, like the MCP OAuth stopgap.
- A production compose profile or published container images. Both are follow-ups.
- Changes to the retrieval, ingestion or MCP contracts.

## Decisions

### D1. Playwright, full stack, seeded by the smoke fixture

The e2e suite uses **Playwright** (`@playwright/test`) under `services/admin-ui/e2e/` and runs against the compose stack at `http://localhost:${OPENCG__ADMIN_UI__HOST_PORT:-3000}`.

The suite seeds data with a global setup that reuses the smoke runner's fixture helpers. It builds the uniquely named local git repo from `tests/smoke/fixtures/knowledge-repo`, ingests it with the chat stub, and exports the run's `source_uri` prefix. Tests assert only against entities, candidates and vocabulary that the current run created, following the smoke-testing "current-run assertions" rule. That keeps destructive tests (tombstone, promote, reject) safe on a shared developer stack.

*Alternatives:*

- **Mock the pipeline** with a stub HTTP server and run `next start` alone. Faster and needs no Docker, but the admin UI's server components call the pipeline directly, so a mock duplicates the pipeline contract and misses real integration bugs. It is rejected as the primary tier. The existing Vitest component tests already cover rendering in isolation.
- **Cypress.** Playwright has better multi-browser support, built-in trace viewing and simpler CI caching. It is also what the `.gitignore` already anticipates (`playwright-report/`, `test-results/`).

The suite runs on Chromium in CI. Firefox and WebKit can be enabled locally through a project flag.

### D2. Dev tooling in a root uv dependency group

Add `[dependency-groups] dev = [pytest, pytest-asyncio, respx, ruff]` at the workspace root. uv installs the default group on `uv sync`, so a plain sync gets the test tooling. The per-service `test` extras stay for the Docker images that use them, or are removed if nothing does (verify during implementation).

### D2a. Locked Python images (added during phase 2)

The pipeline and ingestion Dockerfiles copy only `pyproject.toml` files and run `uv sync`, so each image build re-resolves dependencies and can drift from `uv.lock`. The images MUST copy `uv.lock` and install with `uv sync --frozen --no-dev`, the Python counterpart of removing the pnpm `--frozen-lockfile` fallback (task 2.8).

### D2b. ESLint CLI instead of `next lint` (added during phase 2)

`next lint` is deprecated in Next 15.5 and removed in Next 16. The admin UI therefore runs `eslint .` against a committed flat config (`eslint.config.mjs`, extending `next/core-web-vitals` and `next/typescript` through `FlatCompat`). The `admin-ui` spec's "Lint is non-interactive" scenario is about `pnpm --filter @opencg/admin-ui lint`, so it holds either way.

### D2c. Non-root images and runtime uv (added during phase 2)

The Python images run as uid 10001 (`opencg`) and set `UV_FROZEN=1` / `UV_NO_SYNC=1`, so `uv run` at runtime, including `compose exec` from `make ingest-git` and the smoke runner, never tries to write to the root-owned `/app`. All runtime writes (git clones, smoke fixtures) go to `/tmp`. The Node images run as `node`. The admin UI sets `HOSTNAME=0.0.0.0` so the Next standalone server is reachable from its own healthcheck.

### D3. CI shape

- `ci.yml`, on push and PR:
  - **`static`**: pnpm and uv caches, `make lint`, `make typecheck`, `make test`, `pnpm build-storybook`, gitleaks.
  - **`stack`** (needs `static`, on PRs to `main` + nightly + manual dispatch): `make up-d`, wait for health, `make smoke`, `make e2e`. Uploads the Playwright report and compose logs on failure. The Ollama model volume is cached by embedding-model name.
- `dependabot.yml`: npm, pip/uv, github-actions and docker ecosystems, weekly.

### D4. Safe network defaults

Every published compose port becomes `"127.0.0.1:${OPENCG__<SVC>__HOST_PORT:-<default>}:<container>"`. Postgres user, password and db come from `.env` (`OPENCG__POSTGRES__USER` and so on, defaulting to the current values for compatibility), and the pipeline URL is derived from them. Operators who need LAN exposure override the bind address on purpose (`OPENCG__BIND_ADDRESS`).

### D5. MCP host port: one default, documented once

Compose defaults the MCP host port to `8181`, matching README and `CLAUDE.md`. That dodges the common 8080 collision noted in the project gotchas. The container port stays 8080.

### D6. Optional admin access gate

When `OPENCG__ADMIN_UI__PASSWORD` is set, Next middleware requires a session cookie obtained from a `/login` form. That covers every page and every `/api/proxy/**` route. When it is unset, the UI keeps today's behaviour but renders a persistent "unauthenticated — local use only" banner and logs a warning at startup. It is marked `REPLACE-BEFORE-PROD`, like `oauth.ts`. The e2e suite covers both modes.

Implementation notes (phase 3):
- The session cookie is `<issued-at>.<HMAC-SHA256(password, issued-at)>`: HttpOnly, SameSite=Lax, and Secure when the request (or `x-forwarded-proto`) is HTTPS. It expires after 12 hours, and changing the password invalidates every session. It uses Web Crypto only, so the same code runs in middleware and route handlers. Page requests without a session redirect to `/login?next=…`; `/api/**` requests get a 401. `/login`, `/api/auth/*`, `/api/healthz` and the files in `public/` stay open.
- The password is read at runtime, not baked in at build time. Tested on the standalone image: the same build was run with and without it.
- The login and logout handlers send relative `Location` headers. The standalone server binds `0.0.0.0`, so absolute redirects built from `req.url` pointed the browser at `http://0.0.0.0:3000`. Found during live verification.
- `next` is limited to same-origin paths, so `//host` and `/\host` fall back to `/`.

### D7. Smoke-only wiring leaves the default profile

`smoke-chat` and the ingestion service's fixture bind-mount move to a `smoke` compose profile. `make smoke` and `make e2e` enable that profile, so `make up-d` starts only what a real user needs.

## Risks / Trade-offs

- **CI runtime and cost.** The full-stack job pulls about 270 MB of model and builds four images. Mitigation: cache the Ollama volume and image layers, and run it on PRs to `main` and nightly rather than on every push.
- **Flaky browser tests.** The graph view uses a force-directed canvas. Mitigation: assert on the side panel, search results and DOM state, never on canvas pixels. Use Playwright's auto-waiting and `retries: 1` in CI only.
- **Loopback binds break remote-host setups.** Mitigation: `OPENCG__BIND_ADDRESS`, documented in OPERATIONS.
- **Copyright change.** Changing the holder is a legal decision, not a code one. See Open Questions.

## Resolved Questions (Edward, 2026-11-09)

1. **Copyright holder:** `LICENSE` names **Electric Mind**.
2. **Full-stack CI trigger:** every PR targeting `main`, plus nightly and manual dispatch.
3. **`bootstrap-thin-mvp`:** archive as superseded by its follow-up changes.
4. **Git history:** keep as-is, no squash. The earlier names (Cortex, Hive Mind) remain in history and archived specs. A full gitleaks scan is task 1.4.
