## ADDED Requirements

### Requirement: Hydration stability under load

The admin UI SHALL provide a hydration stress check, runnable with `make hydration-stress` against a production build on a seeded stack. It MUST load every admin route from several concurrent browsers and count React hydration errors, other console errors, pages left unhydrated and client navigations that do not commit. It MUST print a summary and exit non-zero when any count is above zero.

#### Scenario: No hydration errors under concurrent load

- **WHEN** `make hydration-stress` runs with its defaults (7 concurrent Chromium browsers, 30 cycles over `/`, `/queries`, `/queries/[id]`, `/vectors`, `/entities`, `/entities/[id]`, `/ingestion` and `/graph`, 1,680 page loads) against the production admin UI image
- **THEN** no load logs React error #418 or any other console error
- **AND** every load leaves the page's `main h1` hydrated
- **AND** the command exits 0

#### Scenario: Client navigations always commit

- **WHEN** the stress check clicks a sidebar link after each load, and a `/queries` row link once per cycle in each browser
- **THEN** every click reaches its target URL within 5 seconds
- **AND** the summary reports zero stuck sidebar navigations and zero stuck row navigations

#### Scenario: Missing seed data fails clearly

- **WHEN** the stress check starts and `/queries` or `/entities` has no rows to take a detail id from
- **THEN** it exits non-zero with a message saying to seed the stack (for example with `make smoke`) first, without running any load cycles

#### Scenario: Nightly regression guard

- **WHEN** the CI `stack` job runs on its nightly schedule
- **THEN** it runs the stress check with 4 browsers and 10 cycles after the e2e suite and fails the job if any counter is above zero
- **AND** it uploads the JSON summary as an artifact

### Requirement: Supported framework baseline

The admin UI SHALL run on an exact-pinned Next.js 16 release that includes the fixes for every Next.js security advisory fixed in the release it replaces. It SHALL declare `react`, `react-dom`, `@types/react` and `@types/react-dom` at major version 19, and the workspace SHALL require Node.js 20.9.0 or later. Request-time APIs MUST be accessed asynchronously.

#### Scenario: Versions are declared

- **WHEN** `services/admin-ui/package.json` and the root `package.json` are read
- **THEN** `next` and `eslint-config-next` are pinned to the same exact 16.x version, the four React packages are at major version 19, and `engines.node` is `>=20.9.0`

#### Scenario: Proxy file convention

- **WHEN** the production build runs
- **THEN** the access gate is defined in `src/proxy.ts` with an exported `proxy` function, no `src/middleware.ts` exists, and the build prints no `middleware` deprecation warning

## MODIFIED Requirements

### Requirement: End-to-end browser test suite

The admin UI SHALL have a Playwright end-to-end suite under `services/admin-ui/e2e/` that drives every route in a real browser against the running compose stack. The suite MUST seed its own data from the committed smoke fixture with a unique run identifier, and every assertion and mutation MUST target only entities, candidate relationships and vocabulary entries created by the current run. The suite MUST be runnable with `make e2e` and MUST NOT call an external chat provider.

#### Scenario: Every route renders against live services

- **WHEN** `make e2e` runs against a healthy stack
- **THEN** `/`, `/queries`, `/queries/[id]`, `/vectors`, `/entities`, `/entities/[id]`, `/ingestion` and `/graph` each load without an error boundary, an uncaught console error or a failed same-origin request
- **AND** sidebar navigation reaches each page

#### Scenario: Hydration errors are never tolerated

- **WHEN** any route logs a React hydration error (including minified error #418) during the suite
- **THEN** the test fails on that load
- **AND** the suite does not reload, retry or annotate its way past the error

#### Scenario: Vector search finds seeded content

- **WHEN** the test searches `/vectors` for the fixture's unique retrieval phrase
- **THEN** a result from the current run's `source_uri` prefix appears with a score and snippet

#### Scenario: Retrieval appears in the query log

- **WHEN** the test issues a retrieval through the pipeline and then opens `/queries`
- **THEN** a row with the test's correlation ID is listed
- **AND** its detail page shows token counts and fragments

#### Scenario: Entity browse, detail and tombstone

- **WHEN** the test filters `/entities` to the current run, opens a chunk and confirms the tombstone action
- **THEN** the detail page shows the entity as tombstoned
- **AND** a subsequent vector search no longer returns that chunk

#### Scenario: Ingestion run from the UI

- **WHEN** the test submits the "Run now" form on `/ingestion` with the run's local fixture repository
- **THEN** a new run appears in the run list and reaches a terminal success state within the suite timeout

#### Scenario: Graph review flows

- **WHEN** the test searches a fixture concept on `/graph`, opens its detail, promotes one current-run candidate relationship, rejects another and adds a vocabulary entry
- **THEN** each change is reflected in the UI after reload
- **AND** no candidate or vocabulary entry outside the current run is modified

#### Scenario: Theme toggle persists

- **WHEN** the test switches the theme and reloads
- **THEN** the selected theme is still applied

#### Scenario: Failures leave evidence

- **WHEN** an e2e test fails in CI
- **THEN** the Playwright HTML report, trace and screenshot are uploaded as build artifacts

### Requirement: Clean-checkout build

The admin UI's production image, `next build`, `tsc --noEmit`, the ESLint CLI (`pnpm lint`) and `build-storybook` SHALL all succeed from a clean checkout with no untracked files, and none of them MAY prompt for interactive input. None of them MAY modify a tracked file.

#### Scenario: Storybook builds from a clean clone

- **WHEN** a contributor clones the repo, runs `make bootstrap` and then `pnpm --filter @opencg/admin-ui build-storybook`
- **THEN** the build exits 0

#### Scenario: Lint is non-interactive

- **WHEN** `pnpm --filter @opencg/admin-ui lint` runs in a non-TTY environment
- **THEN** it uses the committed ESLint configuration and exits without prompting

#### Scenario: Build leaves the tree clean

- **WHEN** a contributor runs `pnpm --filter @opencg/admin-ui build` on a clean checkout
- **THEN** `git status --porcelain` reports no modified tracked files afterwards (in particular `tsconfig.json` and `next-env.d.ts` are already in the form Next writes)
