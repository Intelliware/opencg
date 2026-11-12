## ADDED Requirements

### Requirement: OPA policy service

The compose `dev` profile SHALL include an Open Policy Agent service, pinned to an exact image tag, serving `infra/opa/policies/` and `infra/opa/data/` mounted read-only. It MUST be healthchecked, MUST bind to loopback on `${OPENCG__OPA__HOST_PORT:-8281}`, and MUST be reachable at `OPENCG__OPA__URL` (default `http://opa:8181`). The pipeline's `/readyz` MUST fail when OPA is unreachable.

#### Scenario: OPA is part of the default stack

- **WHEN** an operator runs `make up-d`
- **THEN** the `opa` service starts and reports healthy
- **AND** the pipeline's `/readyz` returns `200`

#### Scenario: Readiness fails without OPA

- **WHEN** the `opa` service is stopped
- **THEN** the pipeline's `/readyz` returns `503` naming `opa`

### Requirement: Policy packages and revision

The policies SHALL define two packages: `opencg.entitlement` (retrieval candidates) and `opencg.admin` (API actions). Every decision MUST return the deciding `package` and the policy `revision`. The revision MUST be the SHA-256 of the policy and data files, recorded in `infra/opa/data/opencg.json` as `meta.revision`, and `make opa-test` MUST fail when the recorded revision is stale.

#### Scenario: Stale revision is caught

- **WHEN** a contributor edits `infra/opa/policies/entitlement.rego` without running `make opa-revision`
- **THEN** `make opa-test` fails and names the expected revision

#### Scenario: Decisions carry the revision

- **WHEN** the pipeline requests an entitlement decision
- **THEN** the response contains `package = "opencg.entitlement"` and the current `meta.revision`

### Requirement: OPA-backed entitlement policy

The retrieval pipeline SHALL submit every retrieved candidate to `opencg.entitlement` with the input `{ principal, request, candidates }`, where `principal` carries `id`, `roles`, `tenant` and `auth_method`, and each candidate carries `entity_id`, `classification`, `source` and `source_uri`. The policy MUST return `{allow, reason}` per `entity_id`. Decisions MUST be requested once per request and MUST NOT be cached across requests.

#### Scenario: Policy denies access

- **WHEN** OPA returns `{ allow: false, reason: "classification_restricted" }` for a candidate
- **THEN** the candidate is excluded from the assembled context
- **AND** the audit record contains the policy package, revision, decision and reason for that candidate

#### Scenario: No decision reuse across requests

- **WHEN** the same principal sends the same query twice
- **THEN** the pipeline requests entitlement decisions from OPA for each request

### Requirement: Default entitlement rules

The default policy SHALL allow `public` and `internal` candidates to principals with `reader` or `admin`, and MUST allow `confidential:<domain>` candidates only to principals holding the role `<domain>`. It MUST deny any other classification with `reason = "unknown_classification"`, and MUST deny every candidate to a principal with no recognised role with `reason = "no_role"`. The mapping MUST live in `infra/opa/data/opencg.json` so operators change it without editing Rego.

#### Scenario: Confidential content needs the matching role

- **WHEN** a candidate is classified `confidential:legal` and the principal has roles `["reader"]`
- **THEN** the candidate is denied with `reason = "classification_restricted"`
- **AND** the same candidate is allowed for a principal with roles `["reader","legal"]`

#### Scenario: Unknown classification is denied

- **WHEN** a candidate is classified `secret` and the default data defines no rule for it
- **THEN** the candidate is denied with `reason = "unknown_classification"`, whatever the principal's roles

### Requirement: Fail-closed policy evaluation

When OPA is unreachable, exceeds `OPENCG__OPA__TIMEOUT_MS` (default 2000), or returns no decision for some candidate or action, the calling service SHALL treat the request as denied. `/retrieve` MUST respond `503` with `code = "policy_unavailable"` and no fragments, and MUST still write an `audit_log` row with `outcome = "error"`. Admin endpoints MUST respond `503` with the same code without performing the action.

#### Scenario: OPA down blocks retrieval

- **WHEN** OPA is stopped and a client calls `POST /retrieve`
- **THEN** the response is `503` with `code = "policy_unavailable"`
- **AND** an `audit_log` row is written with `outcome = "error"` and `error_code = "policy_unavailable"`

#### Scenario: Partial decision set is treated as deny

- **WHEN** OPA returns decisions for 9 of 10 candidates
- **THEN** the pipeline responds `503` with `code = "policy_unavailable"` and returns no fragments

### Requirement: Access audit log

A new append-only table `opencg.access_audit_log` SHALL record API authorization decisions, with columns `id BIGSERIAL`, `created_at TIMESTAMPTZ`, `correlation_id`, `service`, `principal`, `roles TEXT[]`, `tenant`, `auth_method`, `action`, `resource`, `decision` (`allow` or `deny`), `reason`, `policy_package` and `policy_revision`. A row-level trigger MUST forbid `UPDATE` and `DELETE`. The init script MUST be safe to re-run against an existing database.

#### Scenario: Access audit rows are immutable

- **WHEN** any code path attempts to `UPDATE` or `DELETE` a row in `access_audit_log`
- **THEN** the database raises an error and the operation fails

#### Scenario: Re-running the init script is safe

- **WHEN** `070_access_audit.sql` is applied to a database that already has the table
- **THEN** it completes without error and existing rows are untouched

### Requirement: What the access audit log records

A row SHALL be written to `access_audit_log` for every `deny` and for every `allow` of a state-changing action (`entity.tombstone`, `graph.write`, `vocab.write`, `ingestion.run`), in the same transaction as the action when the action writes to Postgres. Allowed read actions and authentication failures MUST NOT be written to this table.

#### Scenario: Denied tombstone is recorded

- **WHEN** a principal with roles `["reader"]` calls `DELETE /entities/{id}`
- **THEN** the response is `403` and the entity is unchanged
- **AND** an `access_audit_log` row records the principal, `action = "entity.tombstone"`, `resource = <id>`, `decision = "deny"` and the policy's reason

#### Scenario: Allowed write is recorded with the real actor

- **WHEN** a principal `alice` with role `admin` promotes a candidate edge
- **THEN** an `access_audit_log` row records `principal = "alice"`, `action = "graph.write"`, `decision = "allow"`

#### Scenario: Reads and bad tokens are not recorded

- **WHEN** a reader lists entities, and separately a client sends an expired token
- **THEN** no `access_audit_log` row is written for either request

### Requirement: Policy decisions in the retrieval audit record

Every `opencg.audit_log` row written by `/retrieve` SHALL record, for each candidate in `candidate_decisions`, the `decision` (`include`, `deny` or `drop`), the `reason`, and for policy decisions the `policy_package` and `policy_revision`. The row MUST record `auth_method` (`oidc`, `none` or `api_key`) and the principal and roles derived by the pipeline, never values from the request body in `oidc` mode.

#### Scenario: Denied and budget-dropped candidates are distinguishable

- **WHEN** a retrieval returns 10 candidates, the policy denies 2 and the token budget drops 3
- **THEN** `candidate_decisions` lists all 10, with 2 `deny` entries carrying the policy package and revision, 3 `drop` entries with `reason = "budget_exhausted"`, and 5 `include` entries

#### Scenario: Body identity cannot spoof the audit row

- **WHEN** in `oidc` mode a client authenticated as `bob` sends `/retrieve` with `identity.principal = "alice"` in the body
- **THEN** the audit row's principal is `bob`
