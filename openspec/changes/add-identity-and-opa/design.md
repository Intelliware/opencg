## Context

What runs today (`main` after v0.1.0):

| Surface | Authentication | Identity used | Authorization |
|---|---|---|---|
| MCP `/mcp` (HTTP) | Optional static bearer (`OPENCG__MCP__HTTP_TOKEN`) or a token from the stopgap OAuth server (`src/oauth.ts`, one shared password, in-memory) | Stub from `OPENCG__IDENTITY__*`, put in the request body | None |
| MCP stdio | None (local process) | Stub | None |
| Pipeline `:8000` | None | `/retrieve` trusts `identity` in the body; graph writes use `cfg.identity.principal` as `actor` | `assemble.py` maps roles to classifications in code |
| Ingestion `:8100` | None | None | None |
| Admin UI `:3000` | Optional shared password, HMAC cookie (`lib/session.ts`, `middleware.ts`) | None (server calls to the pipeline carry no identity) | None |

Every published port binds to `127.0.0.1` by default, which is what makes the current state acceptable for local use. Entities are all ingested as `internal`. `opencg.audit_log` already has `principal`, `roles` and a JSONB `candidate_decisions` column, and its trigger blocks every update except setting `legal_hold`.

`add-foundation` D6 set the identity propagation contract ("lock the shape now, plug a real verifier in later without touching stages 3–7"). This change plugs in the verifier and the policy engine. It keeps the `IdentityContext` shape (`principal`, `roles`, `tenant`) unchanged.

## Goals / Non-Goals

**Goals**

- One real identity, from an operator-chosen OIDC provider, on every entry point: MCP HTTP, admin UI, pipeline and ingestion APIs.
- Entitlement decided by OPA policy, per retrieval candidate and per admin action, with each decision recorded in an append-only log.
- Remove the shared-secret stopgaps without leaving any deployment silently open.
- `make smoke`, `make e2e` and CI exercise the real OIDC and OPA path with no external IdP and no cloud credentials.
- Local single-user use stays a one-command start.

**Non-Goals**

- Audit query API, replay, legal-hold API (stay in `add-foundation`).
- Multi-tenant isolation, per-tenant policies.
- Entitlements on graph concepts and edges, and syncing source-system ACLs.
- User provisioning (SCIM), an openCG user database, or openCG acting as an IdP.
- `local-prod` profile, mTLS between services, OPA bundle server.

## Decisions

### D1. Two auth modes: `oidc` and `none`

`OPENCG__AUTH__MODE` selects the mode for every service. All services read the same variable, so they cannot disagree.

- **`oidc`**: every request outside health and metrics endpoints needs a valid access token from the configured issuer. Identity comes only from the token.
- **`none`**: today's local mode. Requests run as the stub identity from `opencg.yaml` / `OPENCG__IDENTITY__*`. The admin UI shows the "Unauthenticated mode" banner, and each service logs a startup warning.

OPA entitlement runs in **both** modes, so the stub identity's roles are evaluated by the same policy as a real user's. Turning on OIDC changes who you are, not which rules apply.

Startup checks (each service refuses to start, with a message naming the variable):

- `none` with `OPENCG__BIND_ADDRESS` set to anything other than a loopback address. Compose passes `OPENCG__BIND_ADDRESS` into each service's environment for this check.
- `oidc` without `OPENCG__AUTH__OIDC__ISSUER` or `OPENCG__AUTH__OIDC__AUDIENCE`.
- An unknown mode value.
- A removed stopgap variable is set (`OPENCG__ADMIN_UI__PASSWORD`, `OPENCG__MCP__OAUTH_PASSWORD`), see D12.

`none` is the default in `.env.example` (owner decision, 2026-11-12).

*Alternatives:* `oidc` by default, with the bundled IdP always on. Rejected: it adds Keycloak to every fresh clone and to `make up-d`, and a dev realm with published passwords is not more secure than loopback-only open mode.

### D1a. API keys only in the `dev` environment

Some MCP clients and scripts cannot do OAuth. The owner's rule: API keys may authenticate only when the environment is `dev`.

- `OPENCG__ENVIRONMENT` is one of `dev`, `test`, `staging`, `production`. Unset means `production`, so a forgotten setting fails safe. `.env.example` sets `dev`. CI sets `test`.
- `auth.api_keys` in `opencg.yaml` (or `OPENCG__AUTH__API_KEYS_FILE`) lists `{name, key_sha256, principal, roles}`. Only the SHA-256 of a key is stored. `make api-key NAME=… ROLES=…` prints a new random key once, together with the entry to paste. Keys are sent as `Authorization: Bearer ock_<key>`. The `ock_` prefix tells a key from a JWT without parsing it.
- In `dev`, a valid key authenticates in **both** modes, with the entry's principal and roles, and is audited as `auth_method = "api_key"`. OPA applies the same rules as for any other principal. Comparison is constant-time on the hash.
- In any other environment, a configured key list or `OPENCG__MCP__HTTP_TOKEN` stops every service from starting, naming the setting. A request carrying an `ock_` key gets `401` with reason `api_key_disabled`.
- `OPENCG__MCP__HTTP_TOKEN` becomes a legacy single key: in `dev` it is accepted as the key `mcp-http-token` with the stub identity, so existing local setups keep working.

*Alternatives:* client-credentials everywhere (no API keys at all; simpler, but blocks local tools that cannot do OAuth); API keys in every environment (convenient, but long-lived shared secrets are what bank security reviews reject).

### D2. Generic OIDC; Keycloak bundled in the same workload

openCG speaks plain OIDC and OAuth 2.1 and has no IdP-specific code. Operators point it at Entra ID, Okta, Auth0, Keycloak or any compliant provider. When they don't have one, or for local work, tests and CI, openCG ships its own.

The bundled IdP is **Keycloak** (`quay.io/keycloak/keycloak`, pinned exact tag). The owner wants it containerised and deployed in the same workload as openCG, not run as a separate system:

- It is a service in `infra/compose/docker-compose.yml`, in the same compose project and network as the other services, under an `idp` profile. The Makefile adds that profile automatically when `OPENCG__AUTH__MODE=oidc` and `OPENCG__AUTH__OIDC__ISSUER` points at the bundled Keycloak (the `.env.example` value for `oidc`). So `make up-d`, `make down` and `make down-v` manage it with everything else, and `none` mode never starts it.
- Its state lives in its own `keycloak` database and role on the stack's Postgres (created by an init script, with a password from `.env`), not in an in-container H2 file, so realms, registered clients and sessions survive container restarts. `make down-v` removes it with the other volumes.
- It starts with `start-dev --import-realm` in `dev` and `test`, and with `start --optimized` (HTTP behind the operator's TLS proxy, `KC_PROXY_HEADERS=xforwarded`) in `staging` and `production`.
- The committed realm file `infra/keycloak/realm-opencg.json` is imported at first start:

- Realm roles `admin`, `reader`, `legal`. Users `alice` (admin, reader), `bob` (reader) and `carol` (reader, legal) come from a separate `realm-opencg-dev-users.json`, imported only in `dev` and `test`. Their passwords come from `.env`.
- Client `opencg-admin-ui`: confidential, authorization code with PKCE, redirect URI under the admin UI's URL.
- Clients `opencg-smoke` (`admin`, `reader`), `opencg-smoke-reader` (`reader`) and `opencg-smoke-legal` (`reader`, `legal`): client-credentials service accounts used by smoke and e2e for API calls. Their secrets come from `.env`, never the realm file.
- A client scope that adds audience `opencg` and a flat `roles` claim to every token.
- Anonymous dynamic client registration allowed only from trusted hosts (`localhost`), so MCP clients such as Claude Code can register themselves as the MCP authorization spec expects.

Host port `${OPENCG__KEYCLOAK__HOST_PORT:-8380}` on loopback (8080 collides on the maintainer's machine, see the project gotchas).

*Alternatives:*

- **Dex.** Small and fast, but static users cannot carry groups or roles without an extra connector, and it has no dynamic client registration, so neither role-based tests nor standard MCP OAuth clients would work against it.
- **A mock OIDC server** (for example `mock-oauth2-server`). Fastest in CI and issues any claims on demand, but it proves little about a real IdP flow, and it gives developers nothing realistic to sign in to. The owner chose Keycloak everywhere, CI included.
- **Authentik or Zitadel.** Capable, but heavier to configure from a committed file, and less common in the bank and financial-services estates openCG targets than Keycloak or Entra ID.

Keycloak costs an image pull (~450 MB), roughly 500 MB to 1 GB of RAM, and a 20–40 s cold start. It runs only in `oidc` mode and in CI's stack job.

### D3. Public issuer, internal discovery

Browsers reach the IdP at `http://localhost:8380`; containers reach it at `http://keycloak:8080`. The token's `iss` must be one URL for both. openCG separates the two:

- `OPENCG__AUTH__OIDC__ISSUER`: the public issuer, checked against `iss`, and the base of browser redirects.
- `OPENCG__AUTH__OIDC__INTERNAL_URL` (optional): where server-side code fetches discovery, JWKS and the token endpoint. Defaults to the issuer.

Keycloak is configured with `KC_HOSTNAME` set to the public URL and a dynamic backchannel, so tokens fetched from inside the network still carry the public issuer. With a real IdP the internal URL is simply left unset.

### D4. The MCP server becomes an OAuth resource server

The MCP authorization spec separates the resource server (the MCP server) from the authorization server (the IdP). openCG follows it:

- `/.well-known/oauth-protected-resource` lists the configured issuer in `authorization_servers`. Clients discover the IdP from there and run the OAuth flow with the IdP directly.
- `/mcp` validates the bearer token itself (D6) and answers `401` with a `WWW-Authenticate` header pointing to the protected-resource metadata when the token is missing or invalid.
- The SDK's `mcpAuthRouter`, `src/oauth.ts`, the `/authorize` password form and in-memory token store are deleted.

This needs an IdP that lets MCP clients get a client ID: dynamic client registration (Keycloak, Okta, Auth0), Client ID Metadata Documents, or a pre-registered client the operator configures in the MCP client. Entra ID supports only the last. An OAuth proxy for IdPs that do none of these is deferred; the owner confirmed pre-registration is enough for an Entra ID pilot.

*Alternative:* keep the MCP server as an authorization server and proxy to the IdP (the SDK's `ProxyOAuthServerProvider`, named as the replacement in the stopgap's design). It works with any IdP, but openCG would keep issuing and storing tokens, holding a client store, and owning a security-critical flow that the IdP already provides. Rejected as the default; kept as a possible later fallback.

stdio is unchanged: it runs as a local subprocess under the operator's own account and uses the stub identity in `none` mode. In `oidc` mode the stdio transport reads a token from `OPENCG__MCP__STDIO_TOKEN` and fails each tool call with `unauthenticated` if it is missing or invalid.

### D5. Identity propagation: forward the caller's token; every service validates it

The MCP server forwards the caller's access token to the pipeline as `Authorization: Bearer`. The admin UI's server code does the same with the signed-in user's token. The pipeline validates it again and derives `IdentityContext` from it. The pipeline forwards it once more on the ingestion proxy routes. In `oidc` mode the pipeline **ignores** the `identity` object in a `/retrieve` body; the field stays in the wire type so `none` mode and existing clients keep working.

All tokens carry audience `opencg`: openCG's components are one protected resource behind one audience, so passing the token between them is not the "token passthrough" to third-party APIs that the MCP security guidance forbids. Tokens are never forwarded outside openCG (model providers, git hosts).

*Alternatives:*

- **Signed internal identity assertion** (the MCP server mints a short-lived JWT with its own key). It decouples the pipeline from the IdP, but whoever holds the signing key can assert any identity. A second token format to maintain, too.
- **Shared internal secret plus identity headers.** Simplest, and the weakest: one leaked secret lets anyone on the network act as anyone.

Forwarding keeps one trust anchor (the IdP's keys) and lets each service check identity independently. The cost is that each service fetches and caches the JWKS, which a shared verifier makes cheap (D6).

### D6. One verifier per language, one claim mapping

`packages/shared-py` gains `opencg_shared.auth`: config, a JWKS-caching token verifier, and a FastAPI dependency returning `IdentityContext`. The MCP server uses `jose` (`createRemoteJWKSet`, `jwtVerify`) and the admin UI uses `openid-client`. All three read the same variables:

| Variable | Default | Meaning |
|---|---|---|
| `OPENCG__AUTH__OIDC__AUDIENCE` | `opencg` | Required `aud` value |
| `OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM` | `preferred_username` | Falls back to `sub` when absent |
| `OPENCG__AUTH__OIDC__ROLES_CLAIM` | `roles` | Dotted path, e.g. `realm_access.roles` or `groups` |
| `OPENCG__AUTH__OIDC__TENANT_CLAIM` | empty | Empty means the configured `tenant` |

Validation: signature against JWKS (RS256/ES256 only, `alg=none` and HMAC rejected), `iss`, `aud`, `exp`, `nbf`, with 60 s clock skew. JWKS is cached and refetched on an unknown `kid`, at most once every 30 s. Failures return `401` with a reason code (`token_missing`, `token_expired`, `token_invalid`, `issuer_unreachable`) and increment `opencg_auth_failures_total{service,reason}`; the token itself is never logged.

A principal with none of the roles the policy knows is authenticated but gets nothing: OPA denies with `no_role`.

### D7. OPA as a compose service; policies in `infra/opa/`

```
infra/opa/
  policies/entitlement.rego      package opencg.entitlement
  policies/admin.rego            package opencg.admin
  policies/*_test.rego           opa test cases
  data/opencg.json               role → classification map, action → role map, revision
```

The `opa` service (`openpolicyagent/opa`, pinned exact tag) runs `opa run --server` with both directories mounted read-only, in the `dev` profile, healthchecked on `/health`, published on loopback at `${OPENCG__OPA__HOST_PORT:-8281}` for debugging (8181 is the MCP host port). The pipeline and ingestion read `OPENCG__OPA__URL` (default `http://opa:8181`).

**Default entitlement policy:**

- `public` and `internal` need `reader` or `admin`.
- `confidential:<domain>` needs the role `<domain>` (for example `confidential:legal` needs `legal`).
- Any other classification is denied with `unknown_classification`, so a typo never widens access.

**Revision.** `data/opencg.json` carries `meta.revision`, the SHA-256 of the policy and data files (excluding itself). Every decision echoes `package` and `revision`. `make opa-revision` recomputes it, and `make opa-test` fails when it is stale, so the revision in an audit row always identifies the rules that made the decision.

*Alternatives:* embedding the policy in the pipeline (Python rules or an in-process WASM build). Simpler to deploy, but it loses the property that operators change policy without rebuilding services, and it departs from the `add-foundation` architecture. A remote bundle server is deferred: a mounted directory is enough for single-tenant deployments.

### D8. Per-candidate entitlement: one batched call, before the budget

Retrieval gets a separate **entitle** stage between hybrid retrieval and assemble (span `pipeline.entitle`). It sends one request per retrieval to `POST /v1/data/opencg/entitlement/decisions`:

```json
{"input": {
  "principal": {"id": "alice", "roles": ["admin","reader"], "tenant": "default", "auth_method": "oidc"},
  "request":   {"tool": "retrieve_for_context", "correlation_id": "…"},
  "candidates": [{"entity_id": "…", "classification": "internal", "source": "git", "source_uri": "…"}]
}}
```

The policy evaluates each candidate independently and returns `{"decisions": {"<entity_id>": {"allow": bool, "reason": str}}, "package": "opencg.entitlement", "revision": "…"}`. That one response is the request's decision cache; nothing is cached across requests. Denied candidates are removed **before** the token budget, so they never take budget from allowed ones. `assemble.py` loses its role map and only enforces the budget.

Fail closed: if OPA is unreachable, times out (default 2 s, `OPENCG__OPA__TIMEOUT_MS`) or returns a malformed response, `/retrieve` returns `503` with `code = "policy_unavailable"`, returns no fragments, and still writes an audit row with `outcome = "error"`.

`POST /search/vector` applies the same filter to its hits, so the admin UI cannot show content the signed-in user may not retrieve.

*Alternatives:* one OPA call per candidate (what `add-foundation` literally describes) with a per-request cache. Same semantics, but 20–200 HTTP round trips per retrieval. OPA partial evaluation pushed into Qdrant and Postgres filters is faster for large corpora but much harder to audit per candidate; revisit when a corpus needs it.

### D9. Admin action authorization

Every pipeline route maps to one action: `retrieve`, `search.vector`, `audit.read`, `entity.read`, `entity.tombstone`, `graph.read`, `graph.write`, `vocab.write`, `ingestion.read`, `ingestion.run`. A FastAPI dependency asks `POST /v1/data/opencg/admin/decision` with `{principal, action, resource}` and returns `403` with `code = "forbidden"` and the policy's reason on deny. A route without a mapped action fails a unit test, so new routes cannot skip authorization.

Default policy: `reader` gets `retrieve`, `search.vector`, and every `*.read`; `admin` gets everything. The ingestion service authorizes its own `POST /run/git` with the same helper (`ingestion.run`), so calling port 8100 directly does not bypass policy.

MCP `traverse_graph` maps to `graph.read`. Entitlement on individual concepts and edges is deferred.

### D10. Auditing decisions in append-only logs

- **Retrieval.** Each entry in `opencg.audit_log.candidate_decisions` (already JSONB) gains `policy_package`, `policy_revision` and the policy's `reason`. The row gains a nullable `auth_method` column (`oidc` / `none` / `api_key`). The existing immutability trigger covers both.
- **Admin actions and denials.** New table `opencg.access_audit_log` in `infra/postgres/init/070_access_audit.sql`, with the same trigger semantics as `graph_audit_log` (no `UPDATE`, no `DELETE`). Columns: `id`, `created_at`, `correlation_id`, `service`, `principal`, `roles`, `tenant`, `auth_method`, `action`, `resource`, `decision` (`allow`/`deny`), `reason`, `policy_package`, `policy_revision`. A row is written for every `deny` and every `allow` of a state-changing action. Allowed reads are not logged here (retrievals are already in `audit_log`); authentication failures go to logs and metrics, not the database, so unauthenticated traffic cannot fill it.
- **Graph audit.** `graph_audit_log.actor` becomes the authenticated principal.

There is no migration tool: init scripts run only when the Postgres volume is created. `070_access_audit.sql` is therefore written to be re-runnable (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE OR REPLACE` for the trigger function, guarded trigger creation), and `make db-apply SQL=070_access_audit.sql` applies it to an existing volume. The pipeline's `/readyz` reports `access_audit_log` missing instead of failing writes at request time.

### D11. Admin UI sign-in with `openid-client` and a Valkey session

- `/api/auth/signin` starts authorization code + PKCE with `state` and `nonce`; `/api/auth/callback` exchanges the code server-side through the internal URL; `/api/auth/signout` clears the session and redirects to the IdP's end-session endpoint.
- The session lives in **Valkey** (already in the stack for "cache + session"), keyed by a random ID in an HttpOnly, SameSite=Lax cookie (Secure over HTTPS, as today). It holds the tokens and their expiry and is refreshed with the refresh token shortly before the access token expires. Tokens never reach the browser.
- `middleware.ts` runs in the Node.js runtime (stable in Next 15.5) so it can read Valkey. Unauthenticated page requests redirect to sign-in with a same-origin `next`; `/api/**` gets `401`. `/api/auth/*`, `/api/healthz` and `public/` stay open.
- `lib/api.ts` attaches the session's access token to every pipeline call. A `403` from the pipeline renders a "You don't have permission" state instead of an error boundary.
- The sidebar shows the signed-in principal and a sign-out button. In `none` mode none of this runs and the banner stays.

*Alternatives:* Auth.js (NextAuth v5). Less code for the flow, but its default token-in-cookie session overflows the 4 KB cookie limit with Keycloak's access, refresh and ID tokens, and its future is uncertain after the 2025 hand-over. A cookie-only encrypted session (no Valkey) was rejected for the same size reason.

### D12. Migration from the stopgaps

This is pre-1.0 and the stopgaps were always marked `REPLACE-BEFORE-PROD`, so they are removed, not deprecated over a release. To make sure no deployment silently turns open:

- If `OPENCG__ADMIN_UI__PASSWORD` or `OPENCG__MCP__OAUTH_PASSWORD` is set, the service refuses to start and points to the migration section of `docs/OPERATIONS.md`.
- `OPENCG__MCP__HTTP_TOKEN` keeps working only when `OPENCG__ENVIRONMENT=dev`, as a legacy API key (D1a). In any other environment it is rejected at startup; machine clients use the client-credentials grant from the IdP instead.
- `OPENCG__IDENTITY__*` stays, and is used only in `none` mode.
- `CHANGELOG.md` lists the removed variables under **Breaking**.

Steps for an operator moving from the gate to OIDC are in the Migration Plan below.

### D13. Testing without an external IdP

- **Unit:** Python verifier against locally generated keys (expired, wrong issuer, wrong audience, `alg=none`, unknown `kid`); TS verifier likewise; `respx`-mocked OPA for the entitle stage and the admin dependency; fake `_Pool` for the access audit writer; middleware tests for the admin UI.
- **Policy:** `opa test infra/opa/policies infra/opa/data` runs through the pinned OPA image in CI's `static` job (no new host prerequisite) and as `make opa-test`.
- **Test auth mode.** `make smoke` and `make e2e` read `OPENCG_TEST_AUTH_MODE` (default `oidc`). In `oidc` the smoke and e2e overlays enable the `idp` profile and set `OPENCG__AUTH__MODE=oidc` on every openCG service. `OPENCG_TEST_AUTH_MODE=none` keeps today's lighter path for quick local runs and prints which auth checks it skipped.
- **Smoke:** fetches a token for `opencg-smoke` with the client-credentials grant and sends it on every call. New stages check `401` without a token, the MCP protected-resource metadata, an MCP `tools/call` with a token, a `confidential:legal` fixture copy that is denied to the service account and allowed to `carol` (password grant is disabled, so the smoke uses a second service account `opencg-smoke-legal` with role `legal`), and an `access_audit_log` row for a denied tombstone by a reader-only account (`opencg-smoke-reader`).
- **E2E:** global setup signs in through the Keycloak login page as `alice` (admin) and `bob` (reader) and saves two storage states. `auth.spec.ts` covers redirect to the IdP, sign-in, reader denial of a tombstone, and sign-out. The `admin-ui-gated` instance and its port 3001 are removed from the e2e overlay. API calls from tests use the service account's token.
- **CI:** the `stack` job uses the overlays, so every PR to `main` runs the real OIDC and OPA path. The Keycloak image is cached like the other images.

## Risks / Trade-offs

- **Keycloak start time and size in CI** → only under `idp`; healthcheck on `/health/ready`; image layer caching. A mock IdP for CI remains an option if the job gets too slow.
- **Fail-closed retrieval when OPA is down** → OPA is tiny and local; its health is part of the pipeline's `/readyz`; the error is explicit (`policy_unavailable`), never an empty "successful" answer.
- **Stale JWKS after key rotation** → refetch on unknown `kid`, rate-limited.
- **Dev realm credentials in `.env.example`** → loopback only, documented as dev-only, and the realm import is never used outside the `idp` profile. A risk only if someone exposes the dev IdP on a network.
- **Breaking operators who rely on the stopgaps** → refuse to start with a pointer to the migration steps rather than silently opening.
- **IdPs without DCR (Entra ID)** → MCP clients must be pre-registered; documented, with an Entra ID walkthrough in OPERATIONS.md. The owner confirmed this is enough for the pilot; OAuth proxy deferred.
- **API keys leaking into a shared environment** → keys are refused at startup outside `dev`, stored only as hashes, prefixed `ock_` so secret scanners can match them, and audited as `api_key`.
- **Keycloak sharing the stack's Postgres** → its own database and role with no grants on `opencg`; a Keycloak upgrade can't touch openCG tables. Operators who want it separate set `KC_DB_URL` to another server.
- **Mode drift between services** → one variable, read by all; a mismatch shows up as `401`s in smoke immediately.
- **Policy errors widening access** → unknown classifications and unknown actions are denied by default; `opa test` gates every change.

## Migration Plan

1. Deploy with `OPENCG__AUTH__MODE=none` (no behaviour change except OPA running and the stopgap variables rejected). Remove `OPENCG__ADMIN_UI__PASSWORD` / `OPENCG__MCP__OAUTH_PASSWORD`.
2. Register openCG with the IdP: an admin UI client (code + PKCE), an audience `opencg`, a roles claim, and either DCR or pre-registered clients for MCP.
3. Set `OPENCG__AUTH__MODE=oidc`, the issuer, audience and claim variables, and the admin UI client credentials; restart.
4. Reconnect MCP clients: they now discover the IdP through the protected-resource metadata. claude.ai custom connectors are re-added.
5. Adjust `infra/opa/data/opencg.json` to the organisation's roles and classifications; re-run `make opa-test`.

Rollback: set `OPENCG__AUTH__MODE=none` (loopback only). The new table and audit fields are additive; the stopgap code is gone, so rolling back to the shared-password gate means reverting the release.

## Resolved Decisions (owner, 2026-11-12)

1. **Default mode.** `none` in `.env.example` (D1).
2. **API keys.** Allowed only when `OPENCG__ENVIRONMENT=dev`, in either auth mode (D1a).
3. **IdPs without dynamic client registration.** Pre-registered MCP clients are enough for an Entra ID pilot. No OAuth proxy in this change.
4. **IdP.** Keycloak everywhere, CI included. It is containerised and deployed in the same workload as openCG, with its state on the stack's Postgres (D2).
5. **Classification vocabulary.** `public` / `internal` / `confidential:<domain>` (D7).

## Open Questions

None remaining.
