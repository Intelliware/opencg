## MODIFIED Requirements

### Requirement: Optional bearer-token authentication for HTTP

When `OPENCG__ENVIRONMENT` is `dev`, the HTTP `/mcp` endpoint SHALL accept `OPENCG__MCP__HTTP_TOKEN` as a legacy API key named `mcp-http-token`, compared in constant time, with the stub identity and `auth_method = "api_key"`. A missing or wrong token MUST get HTTP 401 without invoking a tool. In `none` mode with no token or API key configured, `/mcp` MUST be served open with a logged warning. Outside `dev`, a set token MUST stop the server from starting.

The `/healthz`, `/readyz` and `/metrics` endpoints MUST remain unauthenticated in every mode.

#### Scenario: Authenticated request is accepted

- **WHEN** the environment is `dev`, `OPENCG__MCP__HTTP_TOKEN` is set, and a client calls `/mcp` with a matching `Authorization: Bearer` header
- **THEN** the request is handled normally by the MCP transport with `auth_method = "api_key"`

#### Scenario: Missing or wrong token is rejected

- **WHEN** the environment is `dev`, `OPENCG__MCP__HTTP_TOKEN` is set, and a client calls `/mcp` without a matching bearer token
- **THEN** the server responds with HTTP 401 and does not invoke any tool

#### Scenario: Unauthenticated mode is explicit

- **WHEN** the mode is `none` and neither `OPENCG__MCP__HTTP_TOKEN` nor any API key is configured
- **THEN** `/mcp` is served without authentication AND the server logs a warning that the HTTP transport is unauthenticated

#### Scenario: Static token is refused outside dev

- **WHEN** the server starts with `OPENCG__ENVIRONMENT=production` and `OPENCG__MCP__HTTP_TOKEN` set
- **THEN** it exits non-zero naming `OPENCG__MCP__HTTP_TOKEN`

## ADDED Requirements

### Requirement: OAuth protected resource backed by an external authorization server

In `oidc` mode, the MCP server SHALL act as an OAuth 2.1 resource server and MUST NOT issue tokens itself. It MUST serve `/.well-known/oauth-protected-resource` with `resource` set to `${OPENCG__MCP__PUBLIC_URL}/mcp` and `authorization_servers` containing `OPENCG__AUTH__OIDC__ISSUER`. It MUST NOT serve `/authorize`, `/token`, `/register`, `/revoke` or `/.well-known/oauth-authorization-server`.

#### Scenario: Discovery points at the IdP

- **WHEN** a client requests `/.well-known/oauth-protected-resource` in `oidc` mode
- **THEN** the response lists the configured issuer in `authorization_servers`

#### Scenario: Self-issued OAuth endpoints are gone

- **WHEN** a client requests `/.well-known/oauth-authorization-server` or `POST /register` on the MCP server
- **THEN** the server responds `404`

### Requirement: Bearer token required on /mcp in OIDC mode

In `oidc` mode, every `/mcp` request SHALL carry a bearer access token that passes the identity-access token validation. A missing or invalid token MUST produce `401` with a `WWW-Authenticate: Bearer` header whose `resource_metadata` parameter points at the protected-resource metadata URL, and MUST NOT reach any tool.

#### Scenario: Unauthenticated request advertises the metadata

- **WHEN** a client calls `/mcp` without a token in `oidc` mode
- **THEN** the server responds `401` with a `WWW-Authenticate` header containing `resource_metadata="<public url>/.well-known/oauth-protected-resource"`

#### Scenario: IdP-issued token is accepted

- **WHEN** a client calls `/mcp` with a valid access token for audience `opencg` from the configured issuer
- **THEN** `initialize`, `tools/list` and `tools/call` succeed

### Requirement: Caller identity propagation

For every tool call, the MCP server SHALL send the pipeline the caller's identity and a correlation ID. In `oidc` mode it MUST forward the caller's validated access token unchanged as `Authorization: Bearer` on every pipeline request, including `traverse_graph`, and MUST NOT forward it outside openCG. In `none` mode it MUST send the stub identity as before. The correlation ID MUST be the caller's `x-correlation-id` when present and a new UUID otherwise.

#### Scenario: Retrieval runs as the caller

- **WHEN** `alice` calls `opencg/retrieve_for_context` over HTTP with her access token
- **THEN** the pipeline receives her token
- **AND** the resulting `audit_log` row has `principal = "alice"` and `auth_method = "oidc"`

#### Scenario: Caller correlation ID is kept

- **WHEN** a client sets `x-correlation-id: abc-123` on a tool call
- **THEN** the pipeline request and the audit row use `abc-123`

### Requirement: Authorization errors surfaced to MCP clients

A `401`, `403` or `503 policy_unavailable` response from the pipeline SHALL be returned to the MCP client as a tool error (`isError: true`) with `code` `unauthenticated`, `forbidden` or `policy_unavailable` respectively. The per-request span MUST record `principal` and `auth_method`.

#### Scenario: Forbidden is surfaced as a tool error

- **WHEN** a principal without `graph.read` permission calls `opencg/traverse_graph`
- **THEN** the tool result has `isError: true` and `code = "forbidden"`

### Requirement: stdio transport authentication in OIDC mode

In `oidc` mode, the stdio transport SHALL authenticate with the access token in `OPENCG__MCP__STDIO_TOKEN`, validated and propagated exactly as an HTTP token. When the variable is missing or the token is invalid or expired, each tool call MUST fail with `code = "unauthenticated"`; the server MUST still answer `initialize` and `tools/list`. In `none` mode the stdio transport MUST behave as before this change.

#### Scenario: stdio without a token in OIDC mode

- **WHEN** the server runs over stdio in `oidc` mode without `OPENCG__MCP__STDIO_TOKEN` and a client calls `opencg/retrieve_for_context`
- **THEN** the tool result has `isError: true` and `code = "unauthenticated"`

## REMOVED Requirements

### Requirement: Stopgap OAuth authorization for the HTTP transport

**Reason**: Replaced by "OAuth protected resource backed by an external authorization server". The MCP server no longer issues tokens; the operator's IdP does.

**Migration**: Unset `OPENCG__MCP__OAUTH_PASSWORD`, set `OPENCG__AUTH__MODE=oidc` and the issuer variables, register the MCP client with the IdP (dynamic registration or a pre-registered client), and re-add claude.ai custom connectors. See `docs/OPERATIONS.md`.

### Requirement: Shared-password authorization gate

**Reason**: The shared password gave every user the same identity. Users now sign in at the IdP.

**Migration**: Unset `OPENCG__MCP__OAUTH_PASSWORD`; the server refuses to start while it is set.

### Requirement: Static bearer and OAuth tokens both accepted on /mcp

**Reason**: There is no self-issued OAuth token any more. The static bearer remains only in `none` mode, under "Optional bearer-token authentication for HTTP".

**Migration**: In `oidc` mode, machine clients obtain tokens with the IdP's client-credentials grant; interactive clients use OAuth against the IdP.
