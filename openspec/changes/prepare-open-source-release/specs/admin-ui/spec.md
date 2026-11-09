## ADDED Requirements

### Requirement: End-to-end browser test suite

The admin UI SHALL have a Playwright end-to-end suite under `services/admin-ui/e2e/` that drives every route in a real browser against the running compose stack. The suite MUST seed its own data from the committed smoke fixture with a unique run identifier, and every assertion and mutation MUST target only entities, candidate relationships and vocabulary entries created by the current run. The suite MUST be runnable with `make e2e` and MUST NOT call an external chat provider.

#### Scenario: Every route renders against live services

- **WHEN** `make e2e` runs against a healthy stack
- **THEN** `/`, `/queries`, `/queries/[id]`, `/vectors`, `/entities`, `/entities/[id]`, `/ingestion` and `/graph` each load without an error boundary, an uncaught console error or a failed same-origin request
- **AND** sidebar navigation reaches each page

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

The admin UI's production image, `next build`, `tsc --noEmit`, `next lint` and `build-storybook` SHALL all succeed from a clean checkout with no untracked files, and none of them MAY prompt for interactive input.

#### Scenario: Storybook builds from a clean clone

- **WHEN** a contributor clones the repo, runs `make bootstrap` and then `pnpm --filter @opencg/admin-ui build-storybook`
- **THEN** the build exits 0

#### Scenario: Lint is non-interactive

- **WHEN** `pnpm --filter @opencg/admin-ui lint` runs in a non-TTY environment
- **THEN** it uses the committed ESLint configuration and exits without prompting

### Requirement: Optional admin access gate

When `OPENCG__ADMIN_UI__PASSWORD` is set, the admin UI SHALL require an authenticated session for every page and every `/api/proxy/**` route. When it is unset, the UI MUST display a persistent unauthenticated-mode banner and log a startup warning. The gate is a stopgap and MUST be marked `REPLACE-BEFORE-PROD` in source.

#### Scenario: Gate blocks unauthenticated proxy calls

- **WHEN** the password is set and a request without a session calls `DELETE /api/proxy/entities/<id>`
- **THEN** the response is 401 and no request reaches the pipeline

#### Scenario: Login grants access

- **WHEN** the password is set and the user submits the correct password at `/login`
- **THEN** they are redirected to the page they requested and can use it

#### Scenario: Unauthenticated mode is visible

- **WHEN** the password is unset
- **THEN** every page shows the unauthenticated-mode banner
