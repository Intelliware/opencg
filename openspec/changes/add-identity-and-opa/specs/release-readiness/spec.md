## MODIFIED Requirements

### Requirement: Continuous integration gates

The repository SHALL run GitHub Actions workflows that execute lint, type-check, unit tests (TypeScript and Python), OPA policy tests (`make opa-test`, run through the pinned OPA image so no new host tool is needed), the Storybook build and secret scanning on every push and pull request. A full-stack job running compose, smoke and the admin UI e2e suite SHALL run on pull requests targeting `main`, on a nightly schedule and on manual dispatch. The full-stack job MUST run smoke and e2e with the test auth mode `oidc`, against the bundled Keycloak IdP and OPA, and MUST NOT depend on an external IdP.

#### Scenario: Static failures block the PR

- **WHEN** a pull request introduces a ruff error, a TypeScript type error, a failing unit test, a failing or stale-revision policy test, or a broken story
- **THEN** the `static` job fails and its required status check blocks merging

#### Scenario: Full-stack failures are diagnosable

- **WHEN** the full-stack job fails
- **THEN** compose service logs (including the `opa` and `keycloak` services) and the Playwright report are uploaded as artifacts

#### Scenario: Full stack runs the real auth path

- **WHEN** the full-stack job runs on a pull request to `main`
- **THEN** smoke and e2e run with `OPENCG__AUTH__MODE=oidc` against the bundled Keycloak and pass without network access to any IdP outside the stack
