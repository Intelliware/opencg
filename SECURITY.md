# Security policy

## Reporting a vulnerability

**Please do not open a public issue, pull request or discussion for a security problem.**

Report it privately through GitHub: on the repository's **Security** tab, choose **Report a vulnerability** ([direct link](https://github.com/Intelliware/opencg/security/advisories/new)). The report is visible only to the maintainers, and we can work on a fix with you in a private advisory before anything is published. If you can't use GitHub, email [opensource@electricmind.com](mailto:opensource@electricmind.com) instead.

Please include:

- the affected component (MCP server, pipeline, ingestion, admin UI, compose configuration) and the commit or version;
- the steps to reproduce, or a proof of concept;
- the impact as you understand it, for example what an attacker can read, change or reach.

We will acknowledge the report, keep you updated while we investigate, and credit you in the advisory unless you prefer otherwise.

## Supported versions

openCG is pre-1.0. Security fixes land on `main` and in the next release; older releases are not patched.

## Deployment model and known stopgaps

openCG v0 is built to run on a single trusted machine, or a trusted private network, by one operator or a small team. It is **not** hardened for direct internet exposure. Every published port binds to `127.0.0.1` by default (`OPENCG__BIND_ADDRESS`), and the shipped `.env.example` values are for local use only.

These are known, deliberate stopgaps. Reports that only restate them are welcome as discussion but are not vulnerabilities:

| Area | Current behaviour | Planned replacement |
|---|---|---|
| **`none` auth mode (the default)** | Every request runs as the stub identity set in the environment (`OPENCG__IDENTITY__*`, default `local-dev` / `admin,reader` / `default`), and the admin UI shows an "Unauthenticated mode" banner. Services refuse to start in this mode unless `OPENCG__BIND_ADDRESS` is a loopback address. OPA policy still applies. | Use `OPENCG__AUTH__MODE=oidc` with your identity provider for anything shared (see `docs/OPERATIONS.md`). |
| **Bundled Keycloak** | For local, smoke, e2e and CI use. `.env.example` ships public `dev-only-…` passwords and client secrets, and dev users are imported in `dev`/`test`. | Change every value before Keycloak is reachable from a network, or use your own IdP. |
| **API keys** | Named static keys (`ock_…`) and the legacy `OPENCG__MCP__HTTP_TOKEN` are accepted **only** when `OPENCG__ENVIRONMENT=dev`; outside `dev` the services refuse to start if any are configured. | Client-credentials tokens from your IdP. |
| **Entitlement scope** | OPA decides retrieval candidates and every API action. Graph concepts and edges have no per-item entitlement (graph reads need only `graph.read`). Source-system permissions are not inherited. | Follow-up changes. |
| **Multi-tenancy** | Single tenant per deployment; `tenant` comes from configuration or one token claim. | Deferred (`add-foundation`). |
| **Ingestion URL guard** | "Run now" accepts `https`, `ssh`, `git` and `user@host:path` URLs that resolve to public addresses, plus local paths under `OPENCG__INGESTION__GIT__LOCAL_ROOTS`. DNS is checked when the URL is submitted, so DNS rebinding between the check and the clone is not covered. The ingestion CLI is operator-driven and unrestricted. | Network-level egress policy. |
| **Transport security** | Services speak plain HTTP inside the compose network and on loopback. | Terminate TLS at a reverse proxy before exposing anything. |
| **Default credentials** | `.env.example` ships the Postgres password `opencg` and the dev-only Keycloak values. | Change them in `.env` before any shared use. |

## Dependency advisories

CI fails a pull request that introduces a high or critical advisory (`dependency-review`), and Dependabot raises updates weekly. As of 2026-11-10 these moderate and low advisories remain, each needing a major-version upgrade. Most are in development tooling that never ships in an image; the table says which ship:

| Package | Severity | Advisory | Why it remains |
|---|---|---|---|
| `esbuild` (Storybook, `tsx`) | moderate, low | [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99), [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr) | Development only; affects esbuild's dev server. |
| `uuid` (Storybook addon-actions) | moderate | [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq) | Development only; the fix is in v11. |
| `glob` (Storybook docgen) | moderate | [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) | Development only; the fix is in v14. |
| `minimatch` (Storybook docgen, ESLint) | moderate | [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) | Development only; the fix is in v11. |
| `@hono/node-server` (MCP server, via the MCP SDK) | moderate | [GHSA-rmxm-3fg6-px4f](https://github.com/advisories/GHSA-rmxm-3fg6-px4f) | Ships in the MCP server image, but neither the SDK nor openCG calls the vulnerable `serveStatic`; the fix is in v2. |
| `graphifyy` (ingestion) | moderate | [GHSA-pcc4-rvhr-2pr8](https://github.com/advisories/GHSA-pcc4-rvhr-2pr8) (its Fortran extractor's `#include` handling) | Ships in the ingestion image and can be reached by ingesting a repository with Fortran sources. The `<0.9` pin is the archived `adopt-graphifyy` contract, so the upgrade needs its own OpenSpec change. |
