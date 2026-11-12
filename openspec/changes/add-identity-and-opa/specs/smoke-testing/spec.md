## ADDED Requirements

### Requirement: Smoke test auth mode

The smoke runner SHALL read `OPENCG_TEST_AUTH_MODE` (default `oidc`). In `oidc` mode it MUST start the bundled IdP through the smoke overlay, set `OPENCG__AUTH__MODE=oidc` on every openCG service, obtain tokens with the client-credentials grant for `opencg-smoke`, `opencg-smoke-reader` and `opencg-smoke-legal`, and send a token on every call. Token acquisition and IdP readiness MUST each have a stage deadline. In `none` mode it MUST print each auth stage it skips.

#### Scenario: Open-mode smoke still works

- **WHEN** an operator runs `OPENCG_TEST_AUTH_MODE=none make smoke`
- **THEN** the smoke passes without Keycloak
- **AND** its output lists the auth stages it skipped

#### Scenario: IdP not ready is reported

- **WHEN** Keycloak does not become ready within its stage deadline
- **THEN** the smoke exits non-zero naming the `idp` stage and the elapsed time

### Requirement: Authenticated smoke assertions

In `oidc` mode the smoke SHALL verify, using only current-run data: a pipeline call without a token returns `401`; the MCP protected-resource metadata names the dev issuer and an authenticated MCP `tools/call` is audited under the service account; a `confidential:legal` fixture copy is hidden from `opencg-smoke` and returned to `opencg-smoke-legal`; a reader's tombstone returns `403` with an `access_audit_log` row; and the graph promotion's `actor` is the service account.

#### Scenario: Default smoke exercises the real auth path

- **WHEN** an operator runs `make smoke` without setting `OPENCG_TEST_AUTH_MODE`
- **THEN** every check above passes
- **AND** no request is made to an IdP or policy service outside the compose stack

#### Scenario: Entitlement denial is audited

- **WHEN** `opencg-smoke` retrieves with the fixture's unique phrase and the current run's `confidential:legal` copy is among the candidates
- **THEN** the copy is not in `fragments`
- **AND** the `audit_log` row records `deny` for it with the policy package and revision
