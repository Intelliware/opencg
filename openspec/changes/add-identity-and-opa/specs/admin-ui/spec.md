## ADDED Requirements

### Requirement: OIDC sign-in

In `oidc` mode, the admin UI SHALL require a signed-in session for every page and every `/api/proxy/**` route. Sign-in MUST use the authorization code flow with PKCE, `state` and `nonce`, with the code exchanged server-side. Unauthenticated page requests MUST redirect to sign-in and return to the requested same-origin path; `/api/**` requests MUST get `401`. `/api/auth/*`, `/api/healthz` and `public/` MUST stay open.

#### Scenario: Unauthenticated visit goes to the IdP

- **WHEN** a browser without a session opens `/graph` in `oidc` mode
- **THEN** it is redirected to the configured IdP's authorization endpoint
- **AND** after signing in it lands on `/graph`

#### Scenario: Proxy calls need a session

- **WHEN** a request without a session calls `DELETE /api/proxy/entities/<id>`
- **THEN** the response is `401` and no request reaches the pipeline

#### Scenario: Open redirect is refused

- **WHEN** the sign-in flow is started with `next=//evil.example`
- **THEN** after sign-in the user lands on `/`

### Requirement: Server-side session

The admin UI session SHALL be stored server-side in Valkey and referenced by a random identifier in an HttpOnly, SameSite=Lax cookie that is Secure when the request (or `x-forwarded-proto`) is HTTPS. Access, refresh and ID tokens MUST NOT reach the browser. The session MUST refresh the access token before it expires and MUST end when refresh fails.

#### Scenario: Tokens stay on the server

- **WHEN** a signed-in user's browser storage and cookies are inspected
- **THEN** they contain only the session identifier, no token

#### Scenario: Failed refresh ends the session

- **WHEN** the refresh token has been revoked at the IdP and the access token expires
- **THEN** the next page request redirects to sign-in

### Requirement: Sign-out and signed-in user display

The sidebar SHALL show the signed-in principal and a Sign out button in `oidc` mode. Sign-out MUST delete the server-side session and redirect to the IdP's end-session endpoint.

#### Scenario: Sign-out ends the session

- **WHEN** a signed-in user clicks Sign out and then opens `/ingestion`
- **THEN** they are sent to sign in again

### Requirement: Pipeline calls carry the user's identity

In `oidc` mode, every server-side call from the admin UI to the pipeline (server components and `/api/proxy/**` route handlers) SHALL carry the signed-in user's access token as `Authorization: Bearer`. A `403` from the pipeline MUST render a permission-denied message naming the action, not an error boundary, and a `401` MUST send the user to sign in.

#### Scenario: Reader sees a permission message

- **WHEN** a user with only the `reader` role confirms a tombstone on `/entities/[id]`
- **THEN** the page shows a "You don't have permission" message
- **AND** the entity is not tombstoned

#### Scenario: Actions are attributed to the user

- **WHEN** `alice` promotes a candidate edge from `/graph`
- **THEN** the resulting `graph_audit_log` row has `actor = "alice"`

### Requirement: Unauthenticated-mode banner

In `none` mode, every page SHALL show a persistent banner stating that the UI is unauthenticated and for local use only, and the admin UI MUST log a startup warning. No sign-out control is shown in this mode.

#### Scenario: Unauthenticated mode is visible

- **WHEN** the auth mode is `none`
- **THEN** every page shows the unauthenticated-mode banner and no sign-out button

### Requirement: End-to-end coverage of sign-in and authorization

When the test auth mode is `oidc`, the Playwright suite SHALL sign in through the bundled IdP's login page as an admin user and as a reader-only user in global setup, and save one storage state per user. It MUST cover: an unauthenticated visit redirected to the IdP and back, a wrong password refused by the IdP, a reader's denied tombstone, an admin action attributed to that user, and sign-out. Direct API calls from tests MUST use a service-account token.

#### Scenario: Auth flows pass against the bundled IdP

- **WHEN** `make e2e` runs with the default test auth mode
- **THEN** the sign-in, reader-denial, attribution and sign-out tests pass against the bundled Keycloak
- **AND** no request is made to an IdP outside the compose stack

### Requirement: E2E in open mode

When the test auth mode is `none`, the sign-in and authorization tests SHALL be skipped with a stated reason, and the unauthenticated-mode banner test MUST run instead.

#### Scenario: Open-mode run skips auth tests visibly

- **WHEN** `OPENCG_TEST_AUTH_MODE=none make e2e` runs
- **THEN** the sign-in tests are reported as skipped with a reason and the banner test passes

## REMOVED Requirements

### Requirement: Optional admin access gate

**Reason**: The shared-password gate is replaced by OIDC sign-in with per-user identity. Its unauthenticated-mode banner moves to the new "Unauthenticated-mode banner" requirement.

**Migration**: Unset `OPENCG__ADMIN_UI__PASSWORD` (the admin UI refuses to start while it is set), register an `opencg-admin-ui` client with the IdP, and set `OPENCG__AUTH__MODE=oidc` with the issuer and admin UI client variables. The `admin-ui-gated` e2e instance is removed.
