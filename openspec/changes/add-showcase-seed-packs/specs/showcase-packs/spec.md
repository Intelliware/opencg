## ADDED Requirements

### Requirement: Synthetic showcase packs

The repository SHALL ship demo content packs `wealth`, `payments` and `retail` under `demo/packs/`, and a shared `group` folder that every seed run ingests. Each pack SHALL contain `public/`, `internal/` and `confidential/` folders of Markdown documents, and a `README.md` listing its scripted questions.

#### Scenario: Pack structure

- **WHEN** a pack directory under `demo/packs/` is listed
- **THEN** it contains a `README.md` with the disclaimer and at least one Markdown document in each of `public/`, `internal/` and `confidential/`

### Requirement: Packs are synthetic

All pack content MUST be synthetic: a fictional institution and fictional people, with no client data. Every pack README MUST state that the content is illustrative and not legal or regulatory guidance.

#### Scenario: Disclaimer present

- **WHEN** any `demo/packs/<pack>/README.md` is read
- **THEN** it names the institution as fictional and states the content is not legal or regulatory guidance

#### Scenario: Split answers exist

- **WHEN** `demo/packs/<pack>/questions.json` is read
- **THEN** each pack has at least three questions, each naming the `internal` document that refers to a `confidential` one and the `confidential` document that holds the answer

### Requirement: Demo seeding

`make demo-seed PACK=<wealth|payments|retail|all>` SHALL ingest each classification folder as a separate run (`public`, `internal`, and `confidential` as `confidential:<pack>`), under the source URI prefix `git://opencg-demo-<pack>-<classification>/`. It SHALL create the demo roles and personas in the bundled Keycloak idempotently, and SHALL refuse to run unless `OPENCG__ENVIRONMENT` is `dev`.

#### Scenario: Classification per folder

- **WHEN** `make demo-seed PACK=payments` completes
- **THEN** every entity under `git://opencg-demo-payments-confidential/` has classification `confidential:payments`, and every entity under `git://opencg-demo-payments-internal/` has classification `internal`

#### Scenario: Seeding is repeatable

- **WHEN** `make demo-seed PACK=all` runs twice
- **THEN** the second run creates no duplicate entities, roles or users, and exits zero

#### Scenario: Refused outside dev

- **WHEN** `make demo-seed` runs with `OPENCG__ENVIRONMENT=production`
- **THEN** it exits non-zero before ingesting anything or changing Keycloak

### Requirement: Demo reset

`make demo-reset PACK=…` SHALL tombstone the pack's entities, and the concepts whose only sources are those entities.

#### Scenario: Reset and re-seed

- **WHEN** `make demo-reset PACK=retail` runs and then `make demo-seed PACK=retail`
- **THEN** the retail entities are tombstoned after the reset and live again after the re-seed

### Requirement: Demo personas see different answers

The demo SHALL define the personas `demo-advisor` (`reader`, `wealth`), `demo-payments-ops` (`reader`, `payments`), `demo-branch` (`reader`, `retail`), `demo-compliance` (`reader`, `wealth`, `payments`, `retail`) and `demo-reader` (`reader`). The OPA policy data SHALL list `wealth`, `payments` and `retail` as confidential domains.

#### Scenario: Domain persona sees the specifics

- **WHEN** `demo-payments-ops` retrieves a scripted payments question
- **THEN** the fragments include the question's `confidential:payments` document

#### Scenario: Reader gets the referral only

- **WHEN** `demo-reader` retrieves the same question
- **THEN** no fragment comes from a `confidential:*` document, and the `internal` document that refers to it is returned

#### Scenario: Domain roles don't cross

- **WHEN** `demo-advisor` retrieves a scripted retail question
- **THEN** no fragment comes from a `confidential:retail` document

### Requirement: Demo guide

`docs/DEMO.md` SHALL cover:
- prerequisites;
- `make demo-up` and `make demo-seed`;
- connecting Claude Code, Claude Desktop and Cursor to the MCP server, with OAuth sign-in as a persona and a per-persona dev API key as fallback;
- a connection check for each tool;
- the per-pack script from `demo/packs/<pack>/questions.json`, with what each persona should see;
- where to find the trace, audit row and cost of a request;
- reset, known limitations and troubleshooting.

The README SHALL link to it.

#### Scenario: Fresh-clone walkthrough

- **WHEN** a presenter follows `docs/DEMO.md` from a fresh clone with Docker running
- **THEN** they can connect at least one AI tool as two different personas and observe a scripted split answer

### Requirement: Demo smoke check

`make demo-smoke` SHALL seed every pack using the deterministic chat stub, then check each pack. For every `(pack, classification)` it SHALL assert the expected entity count. For every scripted question it SHALL assert the split answer for the domain persona and for `demo-reader`. It SHALL then reset. The CI `stack` job SHALL run it on every pull request.

#### Scenario: Persona difference regresses

- **WHEN** a change makes `demo-reader` receive a `confidential:*` fragment for a scripted question
- **THEN** `make demo-smoke` fails and names the question and persona
