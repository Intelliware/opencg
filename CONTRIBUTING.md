# Contributing to openCG

Thanks for helping. This guide covers getting a working checkout, the OpenSpec workflow every change goes through, how to run each test tier, and what a pull request needs.

By taking part you agree to follow the [Code of Conduct](./CODE_OF_CONDUCT.md). Report security problems privately, as described in [`SECURITY.md`](./SECURITY.md), not in issues.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker with Compose v2 | a recent v2 release | Runs the whole stack. The first start downloads the service images and the 262 MB embedding model. |
| Node.js | 22 (20 or newer works) | `corepack enable` provides the pnpm version pinned in `package.json`. |
| pnpm | 9 | Via corepack. |
| Python | 3.12 | uv installs it if it is missing. |
| [uv](https://docs.astral.sh/uv/) | recent | Python workspaces and the dev tools (pytest, ruff). |
| make, git, curl | any | |

## Getting started from a fresh clone

```bash
git clone https://github.com/Intelliware/opencg.git && cd opencg
make bootstrap        # pnpm + uv installs from the lockfiles, plus Playwright's Chromium
cp .env.example .env  # local defaults; change the passwords before sharing the stack
make up-d             # build and start the stack (dev profile)
make smoke            # end-to-end check against the running stack, about 10 s
open http://localhost:3000
```

Every published port binds to `127.0.0.1` and can be moved in `.env` if something else already uses it. For example, set `OPENCG__ADMIN_UI__HOST_PORT=3100` or `OPENCG__POSTGRES__HOST_PORT=15432`. The full list is in `.env.example` and [`docs/OPERATIONS.md`](./docs/OPERATIONS.md).

`make help` lists every target.

## The OpenSpec workflow (required)

Every feature, scope change, architectural pivot, significant dependency change, or anything that adds, changes or removes a requirement goes through an [OpenSpec](https://github.com/Fission-AI/OpenSpec) change **before code is written**:

1. `openspec new change <kebab-case-name>`
2. Write `proposal.md`: why, what changes, affected capabilities, impact.
3. Write `design.md` (decisions with alternatives, risks, open questions) and `specs/<capability>/spec.md` (requirements using SHALL/MUST, each with testable WHEN/THEN scenarios).
4. Write `tasks.md`: the implementation checklist, grouped by phase.
5. `openspec validate <name> --strict` must pass.
6. Open the proposal for review and get agreement **before implementing**.
7. Implement phase by phase, ticking tasks as you go. Anything you discover along the way is recorded in the change, not worked around silently.
8. Run the smoke and e2e suites against a live stack.
9. When it ships, `openspec archive <name>` merges the change's spec deltas into `openspec/specs/`.

Tiny fixes that change no requirement or scenario (a typo, a lint fix, a dependency bump) can go straight to code. When in doubt, write the proposal.

The OpenSpec CLI is pinned in the Makefile (`make openspec-validate` runs it with `npx`), so you don't need a global install. Useful commands are `openspec list`, `openspec show <name>` and `openspec list --specs`.

## Tests

| Tier | Command | Needs the stack | What it covers |
|---|---|---|---|
| Lint | `make lint` | no | ESLint and `tsc` for TypeScript; `ruff check` and `ruff format --check` for Python |
| Type-check | `make typecheck` | no | Every TypeScript package, including the e2e suite |
| Unit | `make test` | no | vitest (MCP server, admin UI) and pytest (shared, pipeline, ingestion) |
| Storybook | `make storybook` | no | Static build of every component story |
| Smoke | `make smoke` | yes | Ingests a uniquely named fixture with a deterministic chat stub, then checks retrieval, audit, vector search, tombstoning, the graph and telemetry |
| End-to-end | `make e2e` | yes (started if needed) | Playwright against the admin UI in Chromium |

`make ci-static` runs everything that doesn't need Docker services, exactly as CI's `static` job does. `make ci-stack` starts the stack and runs smoke and e2e, like CI's `stack` job. `make ci` runs both.

### Running the e2e suite

```bash
make e2e      # headless Chromium; the report is in services/admin-ui/playwright-report/
make e2e-ui   # Playwright's UI mode, for writing and debugging tests
```

What the suite does:

- **Overlays.** It applies the smoke and e2e compose overlays (`infra/compose/docker-compose.{smoke,e2e}.yml`). These add a deterministic chat stub, point ingestion's extraction at it so no external provider is ever called, and start a second admin UI with the access gate on, on port 3001.
- **Run-scoped data.** It seeds its own uniquely named fixture. Every assertion and every change it makes (tombstones, promotions, vocabulary edits) targets only that run's data, so it is safe on a stack you use day to day.
- **Teardown.** On teardown it puts ingestion back on your `.env` chat settings. Set `E2E_KEEP_OVERLAY=1` to skip that when re-running often, as `make e2e-ui` does.
- **Gated main instance.** If your main admin UI has `OPENCG__ADMIN_UI__PASSWORD` set, the suite signs in with it and skips the "unauthenticated banner" test.
- **More browsers.** `E2E_ALL_BROWSERS=1` adds Firefox and WebKit locally.

Specs live in `services/admin-ui/e2e/`. Locate elements by role, label or a run-scoped ID, never by position or "the first row". Assert on DOM state, not on canvas pixels: the graph map is a canvas, so test its side panel instead.

## Project conventions

The agent guide ([`AGENTS.md`](./AGENTS.md)) holds the full list. The ones reviewers check most:

- Admin UI components live in `services/admin-ui/src/components/`, and each has a `*.stories.tsx` neighbour.
- Browser code reaches the pipeline only through Next route handlers under `src/app/api/proxy/`.
- Every model call records token usage on its OTel span and in `opencg_tokens_total`.
- The audit logs are append-only, enforced by triggers. Write a new state-transition row instead of updating one.
- Ingest-time extraction is best-effort: an extractor failure is logged and counted, and never fails the ingest.
- Python tests against asyncpg use the fake `_Pool`/`_Conn` pattern (see `services/pipeline/tests/test_catalog.py`).
- New compose ports use `${OPENCG__<SERVICE>__HOST_PORT:-default}` and bind to `${OPENCG__BIND_ADDRESS:-127.0.0.1}`.

`AGENTS.md`, `CLAUDE.md` and `.cursor/rules/opencg.mdc` must keep identical bodies; `make check-agent-guides` enforces it.

## Commits and pull requests

- Branch from `main`, and keep each pull request to one OpenSpec change or one small fix.
- Write commit messages in the imperative ("Add …", "Fix …"), with a body explaining why. Reference the change and task numbers where they apply, such as `prepare-open-source-release 4.12`.
- Never commit `.env` or any real credential. CI runs gitleaks over the whole history (`make secrets-scan` locally).
- Fill in the pull request template. CI must be green: `static` and `dependency-review` on every PR, plus `stack` (smoke and e2e) on PRs into `main`. Merging into `main` needs one approving review with all review threads resolved.
- When a change ships, archive it in the same pull request or the next one.
