# release-readiness Specification

## Purpose

Keep openCG releasable as an open-source project: a fresh clone builds, tests and runs with documented commands; CI gates every change, including a full-stack smoke and end-to-end run; secrets and known critical or high vulnerabilities are kept out of releases; the defaults are safe for local use; and the community files and docs match the running system.

## Requirements

### Requirement: Fresh-clone contract

With only Docker, Node 20+, pnpm and uv installed, a contributor SHALL be able to run `make bootstrap`, `make lint`, `make typecheck`, `make test`, `make up-d`, `make smoke` and `make e2e` from a fresh clone, in that order, with every command exiting 0. No command may rely on globally installed Python or Node tools beyond those four prerequisites.

#### Scenario: Python test tooling installs with the workspace

- **WHEN** a contributor runs `make bootstrap` on a fresh clone
- **THEN** `uv run pytest` and `uv run ruff` are both available without further installs

#### Scenario: Whole-repo gate

- **WHEN** a contributor runs `make ci` on a healthy stack
- **THEN** lint, type-check, unit tests, the Storybook build, smoke and e2e all run, and the target exits non-zero if any fails

### Requirement: Continuous integration gates

The repository SHALL run GitHub Actions workflows that execute lint, type-check, unit tests (TypeScript and Python), the Storybook build and secret scanning on every push and pull request. A full-stack job running compose, smoke and the admin UI e2e suite SHALL run on pull requests targeting `main`, on a nightly schedule and on manual dispatch.

#### Scenario: Static failures block the PR

- **WHEN** a pull request introduces a ruff error, a TypeScript type error, a failing unit test or a broken story
- **THEN** the `static` job fails and its required status check blocks merging

#### Scenario: Full-stack failures are diagnosable

- **WHEN** the full-stack job fails
- **THEN** compose service logs and the Playwright report are uploaded as artifacts

### Requirement: Secret scanning

CI SHALL run gitleaks over the pushed commits, and the full history SHALL pass a gitleaks scan before the first tagged release. A `make secrets-scan` target MUST run the same scan locally.

#### Scenario: Committed key is rejected

- **WHEN** a commit adds a string matching a provider API-key pattern
- **THEN** the secret-scan step fails and names the file and line

### Requirement: No known critical or high vulnerabilities at release

A tagged release SHALL have no open critical or high-severity Dependabot alerts on its default branch. Each remaining alert MUST either be fixed by upgrading or overriding the affected dependency, or be dismissed in GitHub with a written justification (for example, a vulnerable code path that is unreachable, or a development-only tool that is never exposed). CI MUST fail when a pull request introduces a dependency with a known critical or high vulnerability.

#### Scenario: Release is blocked by a critical advisory

- **WHEN** the default branch has an open critical or high Dependabot alert with no recorded dismissal
- **THEN** release task 8.4 is not satisfied and no tag is created

#### Scenario: PR introduces a vulnerable dependency

- **WHEN** a pull request adds or downgrades a dependency to a version with a known critical or high advisory
- **THEN** the dependency-review check fails and names the package and advisory

### Requirement: Safe network defaults

By default, every host port published by the compose stack SHALL bind to `127.0.0.1` and SHALL be configurable through an `OPENCG__<SERVICE>__HOST_PORT` variable. Database credentials MUST come from `.env` rather than literals in the compose file. Services used only for smoke or e2e MUST NOT start under the default `dev` profile.

#### Scenario: Data stores are not exposed on the LAN

- **WHEN** the stack is started with the default `.env`
- **THEN** Postgres, Qdrant, Valkey and Ollama accept connections on loopback only

#### Scenario: Smoke stub is opt-in

- **WHEN** an operator runs `make up-d`
- **THEN** the `smoke-chat` service is not started and the smoke fixture is not mounted into ingestion

### Requirement: Community and governance files

The repository SHALL include `CONTRIBUTING.md` (including the OpenSpec workflow and the fresh-clone commands), `SECURITY.md` (private disclosure route and a list of known stopgaps), `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, issue and pull-request templates, and a `LICENSE` naming the agreed copyright holder.

#### Scenario: Contributor finds the workflow

- **WHEN** a new contributor opens `CONTRIBUTING.md`
- **THEN** it explains the OpenSpec proposal workflow, the `make` targets and how to run the e2e suite

### Requirement: Documentation matches the running system

The README, `docs/OPERATIONS.md` and the agent guides (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/opencg.mdc`) SHALL agree with the compose defaults, the Makefile and `openspec list`. The three agent guides MUST be identical in body.

#### Scenario: Documented ports are real

- **WHEN** a user follows the README's MCP HTTP instructions with the default `.env`
- **THEN** the documented URL responds from the MCP server

#### Scenario: Agent guides stay in sync

- **WHEN** CI compares the bodies of `AGENTS.md`, `CLAUDE.md` and `.cursor/rules/opencg.mdc` (ignoring front matter)
- **THEN** they are identical
