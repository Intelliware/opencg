# mcp-server Specification

## Purpose

Expose openCG's retrieval and graph tools to AI clients over the Model Context Protocol, through stdio and Streamable HTTP, with optional bearer-token and stopgap OAuth authorization for remote use.

## Requirements
### Requirement: MCP tool surface

The MCP server SHALL advertise the same five-tool surface as before (`search`, `retrieve_for_context`, `get_entity`, `traverse_graph`, `submit_feedback`). `retrieve_for_context` remains the canonical retrieval path. **`opencg/traverse_graph` MUST be functional** in this change — the `not_implemented_in_mvp` error path for this specific tool is removed.

The other three tools (`search`, `get_entity`, `submit_feedback`) MUST continue to return `not_implemented_in_mvp` until their respective follow-up changes ship.

#### Scenario: `tools/list` still advertises five tools

- **WHEN** an MCP client calls `tools/list` after this change ships
- **THEN** the server returns the five tools above
- **AND** each tool name is namespaced under `opencg/<tool>`

#### Scenario: `traverse_graph` returns real results

- **WHEN** a client calls `opencg/traverse_graph` with `{concept_id, depth, types?, limit?, include_candidates?}` against a populated graph
- **THEN** the server forwards to the pipeline's `GET /graph/traverse` and returns the resulting `{nodes, edges}` payload
- **AND** the response is the JSON returned by the pipeline (no MCP-side filtering)

#### Scenario: `traverse_graph` rejects unknown concept

- **WHEN** a client calls `opencg/traverse_graph` with a `concept_id` that does not exist
- **THEN** the server returns a structured error with `code = "concept_not_found"`

#### Scenario: Other deferred tools still error

- **WHEN** a client calls `opencg/search`, `opencg/get_entity`, or `opencg/submit_feedback`
- **THEN** the server returns `isError: true` with `code = "not_implemented_in_mvp"`

### Requirement: Streamable HTTP transport

The MCP server SHALL expose the MCP protocol over the Streamable HTTP transport at the path `/mcp` on its existing HTTP server (the same port used for `/healthz` and `/readyz`, configured by `OPENCG__MCP__PORT`), in addition to the existing stdio transport. The stdio transport MUST remain available and unchanged. The tool surface and behaviour MUST be identical across both transports — the same five tools, the same `opencg/<tool>` namespacing, and the same results and error codes.

#### Scenario: HTTP client completes an MCP session over /mcp

- **WHEN** an MCP client connects to `POST /mcp` and performs an `initialize` then `tools/list`
- **THEN** the server responds over the Streamable HTTP transport and returns the same five `opencg/<tool>` tools advertised over stdio

#### Scenario: stdio transport still works

- **WHEN** a client spawns the server as a subprocess and speaks MCP over stdio
- **THEN** the server behaves exactly as before this change (same tools and results)

#### Scenario: Health endpoints remain available

- **WHEN** the HTTP server is serving `/mcp`
- **THEN** `GET /healthz` and `GET /readyz` continue to respond as before on the same port

### Requirement: Optional bearer-token authentication for HTTP

The HTTP `/mcp` endpoint SHALL support optional bearer-token authentication controlled by `OPENCG__MCP__HTTP_TOKEN`. When the variable is set, requests to `/mcp` MUST include an `Authorization: Bearer <token>` header whose token matches; non-matching or missing tokens MUST be rejected with HTTP 401 and MUST NOT reach the MCP handlers. When the variable is unset or empty, `/mcp` MUST be served without authentication AND the server MUST log an explicit warning that the HTTP transport is unauthenticated. The `/healthz` and `/readyz` endpoints MUST remain unauthenticated regardless of the token setting.

#### Scenario: Authenticated request is accepted

- **WHEN** `OPENCG__MCP__HTTP_TOKEN` is set and a client calls `/mcp` with a matching `Authorization: Bearer` header
- **THEN** the request is handled normally by the MCP transport

#### Scenario: Missing or wrong token is rejected

- **WHEN** `OPENCG__MCP__HTTP_TOKEN` is set and a client calls `/mcp` without a matching bearer token
- **THEN** the server responds with HTTP 401 and does not invoke any tool

#### Scenario: Unauthenticated mode is explicit

- **WHEN** `OPENCG__MCP__HTTP_TOKEN` is unset or empty
- **THEN** `/mcp` is served without authentication AND the server logs a warning that the HTTP transport is unauthenticated

### Requirement: Stopgap OAuth authorization for the HTTP transport

The MCP server SHALL provide an OAuth 2.1 authorization surface on its HTTP listener so OAuth-only MCP clients (claude.ai, Claude Desktop's custom-connector GUI) can authenticate. It MUST expose the discovery and flow endpoints the MCP authorization spec requires — authorization-server metadata, protected-resource metadata, authorization, token, dynamic client registration, and revocation — built on the MCP SDK's OAuth router so the protocol (including PKCE) is spec-conformant. The OAuth metadata MUST advertise endpoints under the server's configured public base URL (`OPENCG__MCP__PUBLIC_URL`).

This authorization surface is an explicitly **temporary stopgap**: state MAY be in-memory and identity MAY be a single shared secret. The implementation MUST carry a prominent in-code marker indicating it is to be replaced before production.

#### Scenario: OAuth discovery is advertised

- **WHEN** a client requests `/.well-known/oauth-protected-resource` or `/.well-known/oauth-authorization-server`
- **THEN** the server returns metadata pointing at this server's authorize, token, and registration endpoints under `OPENCG__MCP__PUBLIC_URL`

#### Scenario: An unauthenticated /mcp request advertises how to authenticate

- **WHEN** a client calls `/mcp` with no access token and no static bearer token
- **THEN** the server responds `401` with a `WWW-Authenticate` header referencing the protected-resource metadata URL

#### Scenario: A full OAuth flow yields a working access token

- **WHEN** a client registers (DCR), completes the authorize step with the correct operator password, and exchanges the PKCE-bound code at the token endpoint
- **THEN** the server issues an access token that is accepted on subsequent `/mcp` requests

### Requirement: Shared-password authorization gate

The `/authorize` step SHALL require the operator password configured in `OPENCG__MCP__OAUTH_PASSWORD`. A request presenting the correct password MUST proceed to issue an authorization code bound to the request's PKCE challenge and redirect URI; an incorrect or missing password MUST NOT issue a code. When `OPENCG__MCP__OAUTH_PASSWORD` is not set, the OAuth authorization endpoints MUST be disabled (not silently open).

#### Scenario: Correct password authorizes

- **WHEN** the user submits the correct `OPENCG__MCP__OAUTH_PASSWORD` at the authorize step
- **THEN** the server redirects back to the client with an authorization code

#### Scenario: Wrong password is rejected

- **WHEN** the user submits an incorrect or empty password at the authorize step
- **THEN** no authorization code is issued and the user is not redirected with a code

### Requirement: Static bearer and OAuth tokens both accepted on /mcp

`/mcp` MUST accept **either** an access token issued by this server's OAuth flow **or** the static `OPENCG__MCP__HTTP_TOKEN` (when set), so existing Claude Code / Cursor configurations using the static bearer continue to work unchanged alongside OAuth clients. The stdio transport MUST remain unaffected by all HTTP authentication.

#### Scenario: Static bearer still works

- **WHEN** a client calls `/mcp` with `Authorization: Bearer <OPENCG__MCP__HTTP_TOKEN>`
- **THEN** the request is handled normally without any OAuth flow

#### Scenario: OAuth-issued token works

- **WHEN** a client calls `/mcp` with a valid access token issued by this server's token endpoint
- **THEN** the request is handled normally

