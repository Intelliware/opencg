## 0. Decisions (Edward)

- [x] 0.1 Choose the `LICENSE` copyright holder: **Electric Mind** (decided 2026-11-09)
- [x] 0.2 Choose the full-stack CI trigger: **every PR to `main` + nightly** (decided 2026-11-09)
- [x] 0.3 Decide what happens to `bootstrap-thin-mvp` (24 open tasks): **archive as superseded** (decided 2026-11-09)
- [x] 0.4 Confirm keeping git history as-is: **keep, no squash** (decided 2026-11-09)

## 1. Baseline verification

- [x] 1.1 Fresh-clone into a temp dir and run `pnpm install --frozen-lockfile`, `uv sync`, `make test`, `make lint` and `make up-d`; record every failure in this change's design.md baseline table
- [x] 1.2 Confirm the admin UI Docker build fails on the missing `public/` directory (expected from reading the Dockerfile)
- [x] 1.3 Run `make smoke` on the fresh-clone stack and record its result and duration
- [x] 1.4 Run `gitleaks detect` over the full history and resolve any findings before going further

## 2. Fresh-clone fixes

- [x] 2.1 Add `services/admin-ui/public/` (with favicon and logo) so the Docker build and Storybook static files resolve
- [x] 2.2 Add a root `[dependency-groups] dev` with pytest, pytest-asyncio, respx and ruff; drop the per-service `test` extras if nothing else uses them; refresh `uv.lock`
- [x] 2.3 Add a committed ESLint flat config (`next/core-web-vitals` + TypeScript) and run it with the ESLint CLI (`eslint .`), since `next lint` is deprecated in Next 15.5 and removed in 16; fix the reported issues (see design D2b)
- [x] 2.4 Register jest-dom matcher types for Vitest (`@testing-library/jest-dom/vitest` in setup + tsconfig types) so `tsc --noEmit` passes
- [x] 2.5 Run `ruff check --fix` and `ruff format`, then hand-fix the remaining errors (graph routes take an optional `ReasonBody` instead of a shared default instance, with a new no-body test; the edge-type test compares lists, not sets)
- [x] 2.6 Add a `typecheck` script per TS package and a `make typecheck` target
- [x] 2.7 Update `make bootstrap` to install from the lockfiles (`pnpm install --frozen-lockfile`, `uv sync --all-packages --frozen`, dev group included); Playwright browser install moves to 4.11, once Playwright is a dependency
- [x] 2.8 Remove the `|| pnpm install` lockfile-bypass fallback from the Dockerfiles, so a stale lockfile fails loudly
- [x] 2.9 Add a non-root `USER` and a `HEALTHCHECK` to each service image (compose inherits them, so `mcp-server` and `admin-ui` now report health); add a pipeline-independent `/api/healthz` route to the admin UI
- [x] 2.10 Copy `uv.lock` into the pipeline and ingestion images and install with `uv sync --frozen`, so images use the locked dependency versions (found during phase 2: images currently re-resolve on every build); declare the missing `opencg-pipeline` dependency of `opencg-ingestion`
- [x] 2.11 Add `make test-shared` to `make test` so the `packages/shared-py` tests run (found during phase 2: they were never run by `make test`)

## 3. Compose and security defaults

- [ ] 3.1 Bind every published port to `${OPENCG__BIND_ADDRESS:-127.0.0.1}` using `${OPENCG__<SVC>__HOST_PORT:-default}`, as the project convention requires
- [ ] 3.2 Move the Postgres user, password and database into `.env` / `.env.example`; derive `OPENCG__POSTGRES__URL` from them
- [ ] 3.3 Default the MCP host port to 8181 so it matches the docs (container port stays 8080)
- [ ] 3.4 Move `smoke-chat` and the ingestion fixture mount into a `smoke` profile; have `make smoke` / `make e2e` enable it
- [ ] 3.5 Validate the ingestion "Run now" URL (allow-list `https://`, `git://` and the fixture path; reject `file://` and internal hosts) to limit SSRF
- [ ] 3.6 Implement the optional admin access gate: middleware, `/login`, cookie session, unauthenticated banner, startup warning, `REPLACE-BEFORE-PROD` marker
- [ ] 3.7 Add Storybook stories for the new banner and login form components
- [ ] 3.8 Unit-test the middleware (blocked proxy call, redirect to login, success)

## 4. Admin UI end-to-end suite (Playwright)

- [ ] 4.1 Add `@playwright/test` to admin-ui and create `playwright.config.ts` (baseURL from env, Chromium project, traces on first retry, HTML report, `retries: 1` in CI only)
- [ ] 4.2 Extract the smoke fixture setup and teardown from `tests/smoke/run.sh` into a reusable script; call it from Playwright global setup and export the run ID and `source_uri` prefix
- [ ] 4.3 Add a fixtures module: a pipeline API helper (retrieve, list run-scoped entities and candidates) and a run-scoped data handle
- [ ] 4.4 `navigation.spec.ts`: every route loads, sidebar links work, no console errors or failed requests, theme toggle persists
- [ ] 4.5 `queries.spec.ts`: a retrieval issued via the API appears in `/queries`, and its detail shows tokens and fragments
- [ ] 4.6 `vectors.spec.ts`: the unique fixture phrase returns a current-run hit with score and snippet; an empty query shows the empty state
- [ ] 4.7 `entities.spec.ts`: filter to the run, paginate, open detail and lineage, tombstone a chunk, and verify it no longer appears in vector search
- [ ] 4.8 `ingestion.spec.ts`: connector list renders; "Run now" against the fixture repo reaches success; an invalid URL shows a validation error
- [ ] 4.9 `graph.spec.ts`: concept search, map detail panel, promote one candidate, reject one, add and edit a vocabulary entry, and confirm tab order; assert on DOM and panel state, not canvas pixels
- [ ] 4.10 `auth.spec.ts`: with the gate enabled, an unauthenticated user is redirected and a proxy call returns 401, and login works; with it disabled, the banner is visible
- [ ] 4.11 Add the Playwright browser install to `make bootstrap` (`pnpm --filter @opencg/admin-ui exec playwright install --with-deps chromium`, moved from 2.7); add `make e2e` (starts the stack with the smoke profile if it is not healthy, then runs Playwright) and `make e2e-ui` (Playwright UI mode)
- [ ] 4.12 Run the suite three times in a row on a persistent stack to prove run-isolation and that it is not flaky

## 5. Continuous integration

- [ ] 5.1 `.github/workflows/ci.yml` `static` job: pnpm and uv caches, lint, typecheck, unit tests, Storybook build, and gitleaks on the pushed commits
- [ ] 5.2 `stack` job: compose build with layer cache, Ollama volume cache, `make up-d`, `make smoke`, `make e2e`; upload compose logs and the Playwright report on failure
- [ ] 5.3 Nightly schedule and `workflow_dispatch` for the `stack` job
- [ ] 5.4 Agent-guide sync check: fail if the bodies of `AGENTS.md`, `CLAUDE.md` and `.cursor/rules/opencg.mdc` differ
- [ ] 5.5 Run `openspec validate --all --strict` in CI
- [ ] 5.6 `.github/dependabot.yml` for npm, uv/pip, docker and github-actions
- [ ] 5.7 Enable branch protection on `main` with `static` (and `stack`, per 0.2) as required checks (GitHub settings, done by Edward)
- [ ] 5.8 Add `make ci` to run the whole gate locally

## 6. Community files

- [ ] 6.1 `CONTRIBUTING.md`: prerequisites, the fresh-clone commands, the OpenSpec workflow, testing tiers (unit / Storybook / smoke / e2e), commit and PR expectations
- [ ] 6.2 `SECURITY.md`: private disclosure route and the known stopgaps (stub identity, MCP OAuth stopgap, admin gate)
- [ ] 6.3 `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) with a contact address
- [ ] 6.4 `CHANGELOG.md` (Keep a Changelog) with an `Unreleased` section summarising the archived changes
- [ ] 6.5 Issue templates (bug, feature/proposal pointing to OpenSpec) and a PR template with a checklist (OpenSpec change, tests, smoke, e2e)
- [ ] 6.6 Update `LICENSE` to name Electric Mind; check that the licences of bundled dependencies (graphifyy MIT, Apache AGE, Qdrant, Valkey) are compatible and credited

## 7. Documentation reconciliation

- [ ] 7.1 README: fix the MCP port, the host-run path (`opencg-fabric`), the shipped and in-flight lists (`stabilize-full-smoke` is archived), the test table (add Playwright), and add CI and licence badges and a "Running the tests" section
- [ ] 7.2 Update the "In-flight changes" section in `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/opencg.mdc` to match `openspec list`, keeping all three identical
- [ ] 7.3 `docs/OPERATIONS.md`: bind address, host-port variables, admin gate, the smoke profile, and troubleshooting for a fresh clone
- [ ] 7.4 Fill the `TBD` Purpose sections in `openspec/specs/*/spec.md`
- [ ] 7.5 Archive `bootstrap-thin-mvp` as superseded, recording which follow-up changes cover its open tasks

## 8. Verification and release

- [ ] 8.1 Fresh clone in a temp dir, then `make bootstrap && make ci`; every step green
- [ ] 8.2 `bash tests/smoke/run.sh` on the live stack
- [ ] 8.3 CI green on the PR, including the `stack` job
- [ ] 8.4 Final `gitleaks detect` over the full history, plus the `CLAUDE.md` pre-push grep
- [ ] 8.5 Tag `v0.1.0`, publish GitHub release notes from the CHANGELOG, and set the repo description and topics
- [ ] 8.6 Archive this change (`openspec archive prepare-open-source-release`)
