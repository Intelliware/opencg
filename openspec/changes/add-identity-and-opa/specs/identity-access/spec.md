## ADDED Requirements

### Requirement: Auth mode selection

Every openCG service (MCP server, pipeline, ingestion, admin UI) SHALL read the auth mode from `OPENCG__AUTH__MODE`, which MUST accept exactly `oidc` or `none` and MUST default to `none`. All services MUST derive their behaviour from this one variable.

#### Scenario: Default mode

- **WHEN** a service starts without `OPENCG__AUTH__MODE`
- **THEN** it runs in `none` mode and logs that it is unauthenticated

### Requirement: OIDC mode requires a token

In `oidc` mode, every HTTP request except `/healthz`, `/readyz`, `/metrics`, `/api/healthz` and the admin UI's sign-in routes SHALL carry a valid access token. The request's identity MUST be derived only from that token.

#### Scenario: Missing token is rejected

- **WHEN** a client calls `POST /retrieve` on the pipeline in `oidc` mode without an `Authorization` header
- **THEN** the pipeline responds `401` with `code = "token_missing"`
- **AND** no retrieval runs and no `audit_log` row is written

#### Scenario: Health endpoints stay open

- **WHEN** a client calls `GET /healthz` on any service in `oidc` mode without a token
- **THEN** the service responds `200`

### Requirement: Open mode uses the stub identity

In `none` mode, requests SHALL run as the stub identity configured in `opencg.yaml` / `OPENCG__IDENTITY__*`, and each service MUST log a warning at startup that it is running without authentication.

#### Scenario: Stub identity is audited as such

- **WHEN** a client calls `POST /retrieve` in `none` mode without a token
- **THEN** the request runs as the configured stub principal and roles
- **AND** the resulting `audit_log` row has `auth_method = "none"`

### Requirement: Unsafe configuration is refused at startup

A service SHALL exit non-zero, with a message naming the offending variable, when `OPENCG__AUTH__MODE` is neither `oidc` nor `none`; when the mode is `none` and `OPENCG__BIND_ADDRESS` is not a loopback address (`127.0.0.1`, `::1`, `localhost`); or when the mode is `oidc` and `OPENCG__AUTH__OIDC__ISSUER` or `OPENCG__AUTH__OIDC__AUDIENCE` is empty.

#### Scenario: Open mode on a network address is refused

- **WHEN** a service starts with `OPENCG__AUTH__MODE=none` and `OPENCG__BIND_ADDRESS=0.0.0.0`
- **THEN** it exits non-zero
- **AND** the message names `OPENCG__AUTH__MODE` and `OPENCG__BIND_ADDRESS`

#### Scenario: OIDC mode without an issuer is refused

- **WHEN** the pipeline starts with `OPENCG__AUTH__MODE=oidc` and no `OPENCG__AUTH__OIDC__ISSUER`
- **THEN** it exits non-zero naming `OPENCG__AUTH__OIDC__ISSUER`

### Requirement: Removed stopgap settings are refused

A service SHALL exit non-zero when `OPENCG__ADMIN_UI__PASSWORD` or `OPENCG__MCP__OAUTH_PASSWORD` is set. The message MUST say the shared-secret stopgap was removed and MUST point to the migration section of `docs/OPERATIONS.md`, so no deployment that relied on it silently becomes open.

#### Scenario: Old admin password is refused

- **WHEN** the admin UI starts with `OPENCG__ADMIN_UI__PASSWORD` set
- **THEN** it exits non-zero with a message that the shared-password gate was removed and where the migration steps are documented

### Requirement: Access token validation

In `oidc` mode, every service SHALL validate access tokens as signed JWTs from one configured issuer. It MUST check the signature against the issuer's JWKS, that `iss` equals `OPENCG__AUTH__OIDC__ISSUER`, that `aud` contains `OPENCG__AUTH__OIDC__AUDIENCE`, and that `exp` and `nbf` hold with at most 60 seconds of clock skew. Tokens signed with `none` or an HMAC algorithm MUST be rejected.

#### Scenario: Expired token is rejected

- **WHEN** a client presents a correctly signed token whose `exp` is more than 60 seconds in the past
- **THEN** the service responds `401` with `code = "token_expired"`

#### Scenario: Wrong audience is rejected

- **WHEN** a client presents a token from the configured issuer whose `aud` does not contain the configured audience
- **THEN** the service responds `401` with `code = "token_invalid"`

#### Scenario: Unsigned token is rejected

- **WHEN** a client presents a token with header `alg = none`
- **THEN** the service responds `401` with `code = "token_invalid"`

### Requirement: Issuer discovery and key caching

Discovery, JWKS and token-endpoint requests SHALL use `OPENCG__AUTH__OIDC__INTERNAL_URL` when it is set and the issuer URL otherwise. The JWKS MUST be cached and MUST be refetched when a token names an unknown `kid`, at most once every 30 seconds.

#### Scenario: Key rotation is picked up

- **WHEN** the issuer rotates its signing key and a client presents a token signed with the new key
- **THEN** the service refetches the JWKS once and accepts the token

#### Scenario: Internal URL is used for keys

- **WHEN** the issuer is `http://localhost:8380/realms/opencg` and the internal URL is `http://keycloak:8080/realms/opencg`
- **THEN** the service fetches discovery and JWKS from the internal URL
- **AND** still requires `iss` to equal the public issuer

### Requirement: Authentication failure reporting

A failed token validation SHALL return `401` with exactly one of the codes `token_missing`, `token_expired`, `token_invalid` or `issuer_unreachable`, and MUST increment `opencg_auth_failures_total{service,reason}`. The token MUST NOT be logged.

#### Scenario: Failure is counted

- **WHEN** a client presents an expired token to the pipeline
- **THEN** `opencg_auth_failures_total{service="pipeline",reason="token_expired"}` increases by one
- **AND** the service log does not contain the token

### Requirement: Principal and tenant claim mapping

A validated token SHALL be mapped to the existing `IdentityContext` shape. `principal` MUST come from the claim named by `OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM` (default `preferred_username`), falling back to `sub` when that claim is absent. `tenant` MUST come from `OPENCG__AUTH__OIDC__TENANT_CLAIM` when set, and otherwise from the configured `tenant`.

#### Scenario: Missing principal claim falls back to sub

- **WHEN** the token has no `preferred_username` claim and `sub = "8f2c…"`
- **THEN** the identity's principal is `"8f2c…"`

#### Scenario: Tenant comes from configuration by default

- **WHEN** `OPENCG__AUTH__OIDC__TENANT_CLAIM` is empty and the configured tenant is `default`
- **THEN** the identity's tenant is `default`

### Requirement: Roles claim mapping

`roles` SHALL come from the dotted claim path in `OPENCG__AUTH__OIDC__ROLES_CLAIM` (default `roles`), and MUST be an empty list when the path is absent. A principal with no roles MUST still be authenticated; what it may see is decided by policy.

#### Scenario: Nested roles claim

- **WHEN** `OPENCG__AUTH__OIDC__ROLES_CLAIM=realm_access.roles` and the token contains `{"realm_access":{"roles":["reader","legal"]}}`
- **THEN** the identity's roles are `["reader","legal"]`

#### Scenario: Token without roles is authenticated but entitled to nothing

- **WHEN** a valid token carries no roles claim and the principal calls `POST /retrieve`
- **THEN** the request is authenticated
- **AND** the entitlement policy denies every candidate with `reason = "no_role"`

### Requirement: Bundled identity provider in the same workload

The compose stack SHALL include a pinned Keycloak service in the same compose project and network as the openCG services, storing its state in its own `keycloak` database on the stack's Postgres. `make up-d` MUST start it when `OPENCG__AUTH__MODE=oidc` and the issuer is the bundled Keycloak, and MUST NOT start it in `none` mode. It MUST bind to loopback on `${OPENCG__KEYCLOAK__HOST_PORT:-8380}`, import the committed `opencg` realm, and issue tokens whose `iss` is the public URL.

#### Scenario: Not started in open mode

- **WHEN** an operator runs `make up-d` with the default `.env`
- **THEN** no Keycloak container is started

#### Scenario: Started with the stack in OIDC mode

- **WHEN** an operator sets `OPENCG__AUTH__MODE=oidc` with the bundled issuer and runs `make up-d`
- **THEN** Keycloak starts in the same compose project and becomes healthy
- **AND** `make down` stops it with the other services

#### Scenario: State survives a restart

- **WHEN** an MCP client registers itself and Keycloak's container is then recreated
- **THEN** the registered client still exists

#### Scenario: Service account token works across the network

- **WHEN** a container on the compose network requests a token for `opencg-smoke` from the internal Keycloak URL
- **THEN** the token's `iss` is the public issuer URL and its `aud` contains `opencg`
- **AND** the pipeline accepts it

### Requirement: Development realm contents

The committed `opencg` realm SHALL define realm roles `admin`, `reader` and `legal`. Users `alice` (`admin`, `reader`), `bob` (`reader`) and `carol` (`reader`, `legal`) SHALL be imported only when `OPENCG__ENVIRONMENT` is `dev` or `test`. A client scope MUST add audience `opencg` and a flat `roles` claim to every token the realm issues.

#### Scenario: Roles reach the token

- **WHEN** `bob` signs in to the admin UI through the dev realm
- **THEN** his access token's `roles` claim is `["reader"]`

### Requirement: Development realm clients

The committed `opencg` realm SHALL define a confidential `opencg-admin-ui` client using authorization code with PKCE; client-credentials service accounts `opencg-smoke` (`admin`, `reader`), `opencg-smoke-reader` (`reader`) and `opencg-smoke-legal` (`reader`, `legal`); and anonymous dynamic client registration limited to trusted local hosts.

#### Scenario: Service accounts carry their roles

- **WHEN** a token is requested for `opencg-smoke-legal` with the client-credentials grant
- **THEN** its `roles` claim contains `reader` and `legal`

#### Scenario: MCP clients can register themselves

- **WHEN** an MCP client on `localhost` sends a dynamic client registration request to the dev realm
- **THEN** the realm registers it and returns a `client_id`

### Requirement: Development IdP secrets stay out of git

User passwords and client secrets for the dev realm SHALL come from `.env` and MUST NOT appear in the committed realm file. `.env.example` MUST mark them as development-only values.

#### Scenario: No secrets in the realm file

- **WHEN** the secret scan runs over `infra/keycloak/`
- **THEN** it finds no password or client secret

#### Scenario: No dev users outside dev and test

- **WHEN** the bundled Keycloak starts with `OPENCG__ENVIRONMENT=production`
- **THEN** the `opencg` realm has no users `alice`, `bob` or `carol`

### Requirement: Deployment environment

Every openCG service SHALL read `OPENCG__ENVIRONMENT`, one of `dev`, `test`, `staging` or `production`. An unset value MUST be treated as `production`, and an unknown value MUST stop the service from starting. `.env.example` SHALL set `dev`.

#### Scenario: Unset environment fails safe

- **WHEN** a service starts without `OPENCG__ENVIRONMENT`
- **THEN** it behaves as `production`, including refusing API keys

### Requirement: API keys only in the dev environment

When `OPENCG__ENVIRONMENT` is `dev`, the pipeline, ingestion service and MCP server SHALL accept named API keys, configured as `{name, key_sha256, principal, roles}` and sent as `Authorization: Bearer ock_<key>`, in both auth modes. A matching key MUST authenticate as its entry's principal and roles with `auth_method = "api_key"`, and OPA MUST apply the same rules as for any principal. Raw keys MUST NOT be stored.

#### Scenario: Key accepted in dev

- **WHEN** the environment is `dev`, the mode is `oidc`, and a client sends a configured API key
- **THEN** the request is authenticated as that key's principal and roles
- **AND** the retrieval audit row records `auth_method = "api_key"`

#### Scenario: Keys refuse to start outside dev

- **WHEN** a service starts with `OPENCG__ENVIRONMENT=staging` and at least one API key configured
- **THEN** it exits non-zero naming the API key setting

#### Scenario: Key sent to a non-dev service

- **WHEN** the environment is `production` and a request carries an `ock_` bearer value
- **THEN** the service responds `401` with reason `api_key_disabled`
