## Why

openCG is already public at `github.com/Intelliware/opencg`, but a stranger who clones it today cannot get a clean run. A review on 2026-11-09 against a fresh `pnpm install` + `uv sync` found:

- **The admin UI image and Storybook do not build from a clean checkout.** `services/admin-ui/Dockerfile` copies `services/admin-ui/public`, and Storybook loads static files from it, but no `public/` directory is tracked. `pnpm build-storybook` fails with `Failed to load static files, no such directory: …/admin-ui/public`; `make up-d` hits the same missing path at `COPY --from=build … /public`.
- **`make test-pipeline` / `make test-ingestion` fail on a fresh clone.** `uv sync` does not install the `test` extras, so `uv run … pytest` reports `Failed to spawn: pytest`. `ruff` is not declared anywhere, so `make lint` fails the same way.
- **`make lint` hangs or fails for the admin UI.** No ESLint config exists, so `next lint` opens an interactive setup prompt and exits 1.
- **The type-check is red.** `tsc --noEmit` on the admin UI fails: `toBeInTheDocument` is not on `Assertion` (jest-dom matcher types are not registered for Vitest).
- **Ruff reports 85 errors** (72 auto-fixable).
- **No CI.** There is no `.github/` directory, so nothing runs the unit tests, smoke test, Storybook build or lint on a PR.
- **No end-to-end coverage of the admin UI.** There are 54 component tests (Vitest + jsdom), but nothing drives the real pages (`/`, `/queries`, `/vectors`, `/entities`, `/ingestion`, `/graph`) in a browser against the running stack.
- **Unsafe network defaults for a public project.** Compose publishes Postgres (with password `opencg`), Qdrant, Valkey and Ollama on every host interface, and the admin UI exposes destructive actions (tombstone, ingestion runs, graph promotion and deletion) with no authentication.
- **The docs contradict each other and the code.** The README documents the MCP endpoint at `localhost:8181`, but compose and `.env.example` default to `8080`. The README says `bootstrap-thin-mvp` shipped, yet it is still an active change (63/87 tasks). The README lists `stabilize-full-smoke` as in flight, but it is archived. The "In-flight changes" table in `CLAUDE.md`/`AGENTS.md` is stale. The README's host-run path points to `opencg-fabric`.
- **Missing open-source hygiene.** There is no CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, issue or PR templates, or CHANGELOG. `LICENSE` names `edward` as the copyright holder, while the repo lives under the Intelliware org.

## What Changes

- Make a clean checkout bootstrap, test, lint, type-check and build with documented commands only (`make bootstrap`, `make test`, `make lint`, `make typecheck`, `make up-d`).
- Add a **Playwright end-to-end suite for the admin UI**. It drives every page against the live compose stack, seeded by the deterministic smoke fixture. It includes destructive flows (tombstone, candidate promote and reject, vocabulary edit), each scoped to data created by the current run.
- Add **GitHub Actions CI**: lint, type-check, unit tests (TS + Python) and the Storybook build on every PR, plus a full-stack job (compose up → smoke → Playwright e2e) on PRs to `main` and nightly.
- Harden the defaults: bind infrastructure ports to `127.0.0.1` through `${OPENCG__*__HOST_PORT}` variables, take the Postgres credentials from `.env`, and add an opt-in admin UI access gate with a loud warning when it is disabled.
- Add open-source community files, secret scanning (gitleaks) in CI and as a pre-push recipe, and Dependabot.
- Reconcile the docs: README, `CLAUDE.md`/`AGENTS.md`/`.cursor/rules/opencg.mdc`, `docs/OPERATIONS.md`, and the active-change list (close out or archive `bootstrap-thin-mvp`).

## Capabilities

### New Capabilities

- `release-readiness`: defines the fresh-clone contract, CI gates, secret scanning, safe network defaults and required community files.

### Modified Capabilities

- `admin-ui`: adds an end-to-end browser test suite, the clean-checkout build requirement and an optional access gate.

## Impact

- `services/admin-ui/`: `public/` directory, ESLint config, Vitest/jest-dom typing fix, a new `e2e/` Playwright suite, `playwright.config.ts`, and access-gate middleware.
- `pyproject.toml` / `services/*/pyproject.toml`: a root `dev` dependency group (pytest, pytest-asyncio, respx, ruff) so `uv sync` installs the test tooling.
- `Makefile`: `typecheck`, `e2e`, `ci` and `secrets-scan` targets; `bootstrap` installs dev groups and Playwright browsers.
- `infra/compose/docker-compose.yml`: loopback port binds, configurable host ports and credentials; smoke-only services and mounts move to a `smoke` profile.
- `.github/`: workflows, Dependabot, issue and PR templates.
- Repo root: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, and an updated `LICENSE` holder.
- Docs: README, OPERATIONS, the three agent-guide copies.
- No change to the retrieval, ingestion or MCP wire contracts.
