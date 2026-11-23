## Why

openCG has no real identity. Three stopgaps stand in for it:

- **Admin UI access gate** (`prepare-open-source-release`, D6): one shared password, an HMAC cookie, no per-user accounts. Marked `REPLACE-BEFORE-PROD`.
- **MCP OAuth stopgap** (`add-mcp-oauth-stopgap`): the MCP server is its own OAuth server, gated by one shared password, with tokens held in memory. Marked `REPLACE-BEFORE-PROD`.
- **Stub identity**: every retrieval and every graph edit runs as the principal in `OPENCG__IDENTITY__*` (`local-dev` / `admin,reader`). The pipeline, the ingestion service and their admin endpoints trust whatever identity the request body carries, and have no authentication at all.

Entitlement is a hard-coded role-to-classification map in `stages/assemble.py`. `add-foundation` describes OPA-backed entitlement per candidate, identity propagation, and audit of policy decisions, but none of it has shipped. `SECURITY.md` lists all of this as known stopgaps, and an enterprise (bank, financial services) pilot cannot start until it is replaced.

## What Changes

- **Generic OpenID Connect identity.** openCG trusts one OIDC issuer, configured by URL. It validates access tokens (signature against the issuer's JWKS, `iss`, `aud`, `exp`) and maps configurable claims to `principal`, `roles` and `tenant`. Any standards-compliant IdP works (Entra ID, Okta, Keycloak, Auth0).
- **Two auth modes** (`OPENCG__AUTH__MODE`): `oidc` (real identity) and `none` (today's open, single-user local mode, with the stub identity and a visible banner). `none` is the `.env.example` default, so a fresh clone stays one light command. `none` refuses to start when ports are bound beyond loopback.
- **API keys are dev-only.** A new `OPENCG__ENVIRONMENT` (`dev`, `test`, `staging`, `production`; unset means `production`) names the deployment. Named API keys, each mapped to a principal and roles and stored only as a hash, authenticate requests in either mode, but only when the environment is `dev`. In any other environment a configured API key (including the existing `OPENCG__MCP__HTTP_TOKEN`) stops the service from starting, and machine clients use the IdP's client-credentials grant.
- **A bundled IdP in the same workload**: Keycloak runs as a container in openCG's own compose project, on the same network, with the same `make up` / `make down` lifecycle, its state in its own database on the stack's Postgres. It starts automatically when `OPENCG__AUTH__MODE=oidc` and no external issuer is configured. It imports an `opencg` realm with roles, the admin UI client and service accounts; dev users are imported only when the environment is `dev`. `make smoke`, `make e2e` and CI all use this container, so no external IdP is needed. Operators with Entra ID, Okta or another IdP point openCG at it instead.
- **MCP server as an OAuth resource server.** It publishes protected-resource metadata pointing at the configured IdP, validates bearer tokens itself, and forwards the caller's token to the pipeline. **BREAKING:** the self-issued stopgap OAuth server and its shared password are removed.
- **Pipeline and ingestion authenticate every request** (except health and metrics) in `oidc` mode and derive identity from the token, not the request body.
- **OPA as a compose service** with Rego policies, data and tests in `infra/opa/`. The pipeline asks OPA for a decision on every retrieval candidate (in one batched call per request) before the token budget is applied, and on every admin API action. The same rules apply in both auth modes. OPA unreachable means the request fails closed.
- **Authorization audit.** Per-candidate decisions, with policy package and revision, are written into the existing `opencg.audit_log` row. A new append-only `opencg.access_audit_log` records every denied request and every allowed state-changing admin action, with the real actor. Graph audit rows record the authenticated principal instead of the stub.
- **Admin UI sign-in through OIDC** (authorization code + PKCE, server-side session in Valkey, RP-initiated sign-out). Server-side pipeline calls carry the signed-in user's access token. **BREAKING:** the shared-password gate (`OPENCG__ADMIN_UI__PASSWORD`, `/login` form) is removed.
- **Classification on ingest**: a git run can set the classification of the entities it creates (default `internal`), so entitlement can be exercised and tested end to end.
- **Tests and docs**: Rego unit tests (`opa test`) in CI's `static` job; smoke and Playwright e2e run the `oidc` path against the bundled IdP in CI; `docs/OPERATIONS.md`, README, `SECURITY.md` and `.env.example` updated.

### Deferred (stays in `add-foundation` or later changes)

- Audit query API, replay and the legal-hold API (`entitlement-audit` "Audit query API", "Recreatability").
- Multi-tenant isolation and per-tenant policy bundles (`add-foundation` OQ4). `tenant` stays a single configured value, optionally read from a claim.
- Entitlement on graph concepts and edges. Graph reads get a role check only.
- Inheriting source-system permissions (Confluence spaces, repo ACLs) into classification.
- `local-prod` compose profile, OPA bundle server and decision-log shipping, mTLS between services, OAuth token exchange (RFC 8693).
- An OAuth proxy for IdPs that support neither dynamic client registration nor pre-registered MCP clients. Pre-registered MCP clients are enough for an Entra ID pilot (owner decision, 2026-11-12).

## Capabilities

### New Capabilities

- `identity-access`: auth modes, OIDC token validation and claim mapping, the bundled IdP, startup safety checks, and removal of the shared-secret stopgaps.

### Modified Capabilities

- `entitlement-audit`: OPA policy service, per-candidate entitlement, admin action authorization, and the append-only access audit log.
- `mcp-server`: replaces the bearer-token and stopgap OAuth requirements with an OIDC resource server that propagates the caller's identity.
- `retrieval-pipeline`: request authentication, entitlement enforcement at assembly and in vector search, authenticated actor on graph writes.
- `admin-ui`: replaces the optional access gate with OIDC sign-in; e2e coverage of sign-in and role-based denial.
- `ingestion`: authenticated HTTP surface and a classification on git runs.
- `smoke-testing`: the smoke runs against the authenticated stack.
- `release-readiness`: CI runs policy tests and the full-stack job in `oidc` mode.

## Impact

- **Code**: `services/mcp-server` (drop `oauth.ts`, add token verification), `services/pipeline` (auth dependency, OPA client, new entitle stage, access audit writer), `services/ingestion` (auth dependency, classification), `services/admin-ui` (middleware, sign-in routes, session store, `lib/api.ts` forwards tokens), `packages/shared-py` and `packages/shared` (shared token verifier and config).
- **Infra**: new `opa` and `keycloak` compose services (Keycloak backed by a `keycloak` database on the existing Postgres), `infra/opa/` (policies, data, tests), `infra/keycloak/` (realm import), new `070_access_audit.sql` init script. The e2e overlay's `admin-ui-gated` instance is removed.
- **Dependencies**: `jose` (MCP server), `openid-client` (admin UI), `PyJWT[crypto]` or `joserfc` for Python (chosen in phase 1), OPA and Keycloak images pinned by exact tag.
- **Operators**: `OPENCG__ADMIN_UI__PASSWORD` and `OPENCG__MCP__OAUTH_PASSWORD` are no longer supported; services refuse to start if they are set. claude.ai and other OAuth MCP clients now authenticate against the operator's IdP.
- **Runtime**: one batched OPA call per retrieval (expected low single-digit milliseconds on the compose network). Keycloak adds roughly 20–40 s to a cold start in `oidc` mode and an image pull in CI. It is not started in `none` mode.
