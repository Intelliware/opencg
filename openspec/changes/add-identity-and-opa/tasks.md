## 0. Decisions (Edward, 2026-11-12)

- [x] 0.1 Default auth mode in `.env.example`: `none`
- [x] 0.2 API keys authenticate only when `OPENCG__ENVIRONMENT=dev` (design D1a)
- [x] 0.3 Pre-registered MCP clients are enough for IdPs without dynamic registration; no OAuth proxy
- [x] 0.4 Keycloak everywhere, containerised in the same workload, state on the stack's Postgres (design D2)
- [x] 0.5 Classification vocabulary: `public` / `internal` / `confidential:<domain>`

## 1. Shared auth foundations

- [ ] 1.1 Choose the Python JWT library (`PyJWT[crypto]` or `joserfc`) and record the choice in design.md
- [ ] 1.2 Add `opencg_shared.auth`: auth config (mode, issuer, internal URL, audience, claim names), startup checks (unknown mode, `none` on a non-loopback `OPENCG__BIND_ADDRESS`, missing issuer or audience, removed stopgap variables), JWKS cache with rate-limited refetch on unknown `kid`, token verifier, claim mapping to `IdentityContext`, FastAPI dependency, `opencg_auth_failures_total` counter
- [ ] 1.3 Add `opencg_shared.authz`: OPA client (timeout, fail-closed on unreachable or partial responses), entitlement batch call, admin decision call, access audit row builder
- [ ] 1.4 Unit tests with locally generated keys: valid, expired, `nbf` in the future, wrong issuer, wrong audience, `alg=none`, HMAC, unknown `kid` then rotation, nested roles claim, `sub` fallback, missing roles; startup-check tests for each refusal
- [ ] 1.5 Unit tests for the OPA client with `respx`: allow, deny, timeout, `5xx`, partial decision set
- [ ] 1.6 Add `auth_method` to the shared TS and Python wire types where identity is reported (no change to `IdentityContext` fields)
- [ ] 1.6a `OPENCG__ENVIRONMENT` (unset means `production`) and API keys: `auth.api_keys` / `OPENCG__AUTH__API_KEYS_FILE` entries `{name, key_sha256, principal, roles}`; `ock_` bearer recognition; constant-time hash comparison; startup refusal outside `dev` when any key or `OPENCG__MCP__HTTP_TOKEN` is set; `401 api_key_disabled`; `auth_method = "api_key"`; `make api-key`; unit tests for each case in Python and TS; add the `ock_` pattern to the secrets scan
- [ ] 1.7 Pass `OPENCG__ENVIRONMENT`, `OPENCG__BIND_ADDRESS` and the `OPENCG__AUTH__*` variables into every openCG service in `docker-compose.yml`; add them to `.env.example` and `opencg.yaml` comments

## 2. OPA policies and service

- [ ] 2.1 Write `infra/opa/policies/entitlement.rego` (per-candidate decisions, `no_role`, `classification_restricted`, `unknown_classification`)
- [ ] 2.2 Write `infra/opa/policies/admin.rego` (action → role mapping, default deny for unknown actions)
- [ ] 2.3 Write `infra/opa/data/opencg.json` (role → classification map, action → role map, `meta.revision`)
- [ ] 2.4 Write `*_test.rego` covering every rule and reason, including `confidential:legal` with and without `legal`, unknown classification, unknown action, and empty roles
- [ ] 2.5 Add `make opa-test` (runs `opa test` and the revision check through the pinned OPA image) and `make opa-revision`
- [ ] 2.6 Add the `opa` compose service: pinned image, read-only mounts, healthcheck, loopback port `${OPENCG__OPA__HOST_PORT:-8281}`, `dev` profile
- [ ] 2.7 Add OPA to the pipeline's `/readyz`

## 3. Database

- [ ] 3.1 Write re-runnable `infra/postgres/init/070_access_audit.sql`: `opencg.access_audit_log`, immutability trigger, grants, and `audit_log.auth_method` (`ADD COLUMN IF NOT EXISTS`)
- [ ] 3.2 Add `make db-apply SQL=<file>` for existing volumes; report a missing `access_audit_log` in pipeline `/readyz`
- [ ] 3.3 Tests: the trigger rejects `UPDATE` and `DELETE`; applying the script twice succeeds (against the compose Postgres in smoke, and the fake `_Pool` pattern for the writer)

## 4. Pipeline

- [ ] 4.1 Wire the auth dependency into every route; derive identity from the token in `oidc` mode and ignore the body identity; stub identity in `none` mode
- [ ] 4.2 Add the route → action table and the authorization dependency; unit test that every registered route except health and metrics has an action
- [ ] 4.3 Add the `pipeline.entitle` stage before assemble; remove the role map from `assemble.py`; record per-candidate policy package, revision and reason in `candidate_decisions`; write `auth_method`
- [ ] 4.4 Fail closed: `503 policy_unavailable` from `/retrieve` with an `outcome = "error"` audit row; `503` from admin routes without performing the action
- [ ] 4.5 Apply the entitlement filter to `POST /search/vector` with the `entitlement_filtered` span attribute
- [ ] 4.6 Use the request principal as `actor` for every `graph_audit_log` write
- [ ] 4.7 Write `access_audit_log` rows for denies and allowed state-changing actions, in the action's transaction where it writes to Postgres
- [ ] 4.8 Forward the bearer token on ingestion proxy calls; pass through upstream `401` / `403`
- [ ] 4.9 Tests: token identity beats body identity; denied candidates do not use budget; one OPA call per retrieval; reader `403` on graph writes with no `graph_audit_log` row; vector search entitlement filter; proxy forwards the token; fail-closed audit row

## 5. Ingestion

- [ ] 5.1 Add the auth dependency and `ingestion.read` / `ingestion.run` authorization to the HTTP surface; record `requested_by`
- [ ] 5.2 Add `classification` to `POST /run/git` and `--classification` to the CLI, validated, written to catalogue rows and Qdrant payloads for parents and chunks
- [ ] 5.3 Tests: classification validation and propagation; direct reader call refused and audited; `none` mode unchanged

## 6. MCP server

- [ ] 6.1 Delete `src/oauth.ts`, the `mcpAuthRouter` mount and `/oauth/approve`; remove the OAuth password config
- [ ] 6.2 Add a `jose`-based verifier and claim mapping matching the Python one; startup checks (including `OPENCG__MCP__HTTP_TOKEN` refused in `oidc` mode)
- [ ] 6.3 Serve `/.well-known/oauth-protected-resource` pointing at the issuer; `401` with `WWW-Authenticate` `resource_metadata` on `/mcp`
- [ ] 6.4 Forward the caller's token on every pipeline call, including `traverse`; map pipeline `401` / `403` / `503 policy_unavailable` to tool error codes; add `principal` and `auth_method` to the request span
- [ ] 6.5 stdio in `oidc` mode: read `OPENCG__MCP__STDIO_TOKEN`, fail tool calls with `unauthenticated` when missing or invalid
- [ ] 6.6 Treat `OPENCG__MCP__HTTP_TOKEN` as the legacy dev-only API key `mcp-http-token` (accepted only in `dev`, `auth_method = "api_key"`); accept named API keys on `/mcp` in `dev`
- [ ] 6.7 Tests: metadata shape, `401` header, valid token passes, expired and wrong-audience tokens rejected, token forwarded to the pipeline (mocked), error-code mapping, stdio without a token, removed OAuth routes return `404`

## 7. Admin UI

- [ ] 7.1 Add `openid-client`; implement `/api/auth/signin`, `/api/auth/callback`, `/api/auth/signout` (PKCE, `state`, `nonce`, same-origin `next`, RP-initiated logout)
- [ ] 7.2 Add a Valkey-backed session store with token refresh; HttpOnly, SameSite=Lax, Secure-over-HTTPS cookie
- [ ] 7.3 Rewrite `middleware.ts` for the Node.js runtime: redirect pages, `401` for `/api/**`, open paths unchanged; `none` mode passes through
- [ ] 7.4 Attach the session's access token in `lib/api.ts` and the proxy route handlers; render a permission-denied state on `403`, re-sign-in on `401`
- [ ] 7.5 Remove `lib/session.ts`, the `/login` page and the password form; keep the unauthenticated banner for `none` mode; refuse to start when `OPENCG__ADMIN_UI__PASSWORD` is set
- [ ] 7.6 Show the signed-in principal and Sign out in the sidebar
- [ ] 7.7 Add stories for the user badge, the permission-denied state and the updated banner; remove stories for deleted components
- [ ] 7.8 Unit tests: middleware (redirect, `401`, open paths, open-redirect refusal), session refresh and expiry, token attached to pipeline calls

## 8. Dev IdP and compose

- [ ] 8.0 Postgres init script creating the `keycloak` database and role (password from `.env`, no grants on `opencg`)
- [ ] 8.1 Write `infra/keycloak/realm-opencg.json` (roles, `opencg-admin-ui`, three smoke service accounts, audience and roles client scope, trusted-host DCR policy) and `realm-opencg-dev-users.json` (`alice`, `bob`, `carol`; imported only in `dev`/`test`), with secrets and passwords from environment placeholders
- [ ] 8.2 Add the `keycloak` service to `docker-compose.yml` under the `idp` profile: pinned tag, Postgres-backed (`KC_DB=postgres`), `start-dev --import-realm` in `dev`/`test` and `start --optimized` with proxy headers otherwise, public hostname plus dynamic backchannel, healthcheck, loopback port `${OPENCG__KEYCLOAK__HOST_PORT:-8380}`
- [ ] 8.2a Makefile: add the `idp` profile automatically when `OPENCG__AUTH__MODE=oidc` and the issuer is the bundled Keycloak; `make down` / `down-v` cover it; confirm `none` mode never starts it
- [ ] 8.2b OPERATIONS.md: running with the bundled Keycloak, pointing at an external IdP instead, and an Entra ID walkthrough with pre-registered MCP clients
- [ ] 8.3 Add dev-only Keycloak user passwords and client secrets to `.env.example`, clearly marked; confirm `make secrets-scan` passes
- [ ] 8.4 Verify a token fetched over the compose network carries the public `iss`, `aud = opencg` and the `roles` claim

## 9. Smoke

- [ ] 9.1 Add `OPENCG_TEST_AUTH_MODE` handling to `tests/smoke/lib.sh` and the smoke overlay (`idp` profile, `OPENCG__AUTH__MODE=oidc` on every openCG service)
- [ ] 9.2 Add an `idp` readiness stage and a token stage (client credentials for the three service accounts) with deadlines; send the token on every `curl`
- [ ] 9.3 Add stages: `401` without a token; MCP protected-resource metadata and an authenticated `tools/call`; `confidential:legal` fixture copy denied and allowed; reader tombstone `403` plus `access_audit_log` row; `graph_audit_log` actor is the service account
- [ ] 9.4 In `none` mode, print each skipped auth stage
- [ ] 9.5 Run `make smoke` in both modes and record durations in design.md

## 10. E2E

- [ ] 10.1 Remove `admin-ui-gated` and port 3001 from `docker-compose.e2e.yml`; enable the `idp` profile and `oidc` mode through the overlays
- [ ] 10.2 Global setup: sign in through the Keycloak page as `alice` and `bob`, save two storage states; get a service-account token for direct API calls (`fixtures.ts`, `env.ts`)
- [ ] 10.3 Rewrite `auth.spec.ts`: redirect to the IdP and back, wrong password refused by the IdP, reader's denied tombstone, admin action attributed to `alice`, sign-out; skip with a reason in `none` mode, where the banner test runs
- [ ] 10.4 Update the queries spec's direct retrieval to use the service-account token
- [ ] 10.5 Run `make e2e` in both modes

## 11. CI

- [ ] 11.1 Add `make opa-test` to the `static` job and `make ci-static`
- [ ] 11.2 Run the `stack` job with `OPENCG_TEST_AUTH_MODE=oidc`; cache the Keycloak and OPA images; upload `opa` and `keycloak` logs on failure
- [ ] 11.3 Confirm both jobs pass on a PR to `main`

## 12. Docs

- [ ] 12.1 `docs/OPERATIONS.md`: auth modes; connecting a real IdP (Entra ID, Okta, Keycloak) with required client, audience and roles claim; MCP client registration (DCR vs. pre-registered); the bundled IdP and its users; OPA policies, data, revision and testing; access audit log; applying `070_access_audit.sql` to an existing volume; a migration section from the removed stopgaps
- [ ] 12.2 README: replace the static-token and OAuth-stopgap connection sections with OIDC instructions (Claude Code, Cursor, claude.ai), keep the `none`-mode quick start, update the admin UI pages table and the pipeline stage list (identity → hybrid retrieval → entitle → assemble)
- [ ] 12.3 `SECURITY.md`: remove the stopgap rows that this change resolves; keep what remains (graph entitlement, multi-tenancy, `none` mode)
- [ ] 12.4 `CHANGELOG.md`: list the removed variables and endpoints under **Breaking**
- [ ] 12.5 Update `AGENTS.md`, `CLAUDE.md` and `.cursor/rules/opencg.mdc` identically (stack table: Keycloak dev IdP and OPA; new gotchas: Keycloak and OPA host ports); `make check-agent-guides` passes

## 13. Verify and finish

- [ ] 13.1 `make lint`, `make typecheck`, `make test`, `make opa-test`
- [ ] 13.2 `make up-d` with the default `.env` (no Keycloak started), then `make smoke` and `make e2e` in `oidc` mode
- [ ] 13.3 Manual check: Claude Code connects to `/mcp` over OAuth against the bundled IdP and runs `retrieve_for_context`
- [ ] 13.4 `openspec validate add-identity-and-opa --strict`
- [ ] 13.5 Update `add-foundation` tasks 2.6, 4.3, 5.2, 5.7 and 12.1 to point at this change
- [ ] 13.6 Commit, push, open the PR
