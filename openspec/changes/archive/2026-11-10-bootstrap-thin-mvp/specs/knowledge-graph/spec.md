## MODIFIED Requirements

### Requirement: Named relationship types

In v0 the Apache AGE extension SHALL be loaded and the `opencg` graph SHALL be created at DB init so a follow-up change can add edges without schema migrations. The vocabulary table, relationship CRUD, and traversal API MUST be added by the follow-up change that ships the `knowledge-graph` capability end-to-end.

#### Scenario: AGE is loaded but no edges are reachable in v0

- **WHEN** the operator inspects the database schema in the thin MVP
- **THEN** the `ag_catalog` schema is present and the `opencg` AGE graph exists
- **AND** no API exposes graph traversal in v0

### Requirement: Automatic relationship extraction

The system SHALL NOT run any relationship extractor in v0. Ingestion MUST write entities and vectors only.

#### Scenario: No extractor runs during v0 ingestion

- **WHEN** a document is ingested in the thin MVP
- **THEN** no relationship extractor is invoked
- **AND** no candidate edges are written

### Requirement: Review, promote, edit, and delete

The system SHALL NOT expose any candidate-edge review, promote, edit, or delete API in v0. A follow-up change MUST add these operations together with the audit-row emission for each state transition.

#### Scenario: No review queue exists in v0

- **WHEN** an operator looks for a candidate-edge review queue in v0
- **THEN** no such surface exists and no API responds to candidate-related CRUD calls

### Requirement: Graph traversal API

The MCP `opencg/traverse_graph` tool SHALL return `not_implemented_in_mvp` in v0. A follow-up change MUST replace this with a working traversal implementation backed by AGE.

#### Scenario: `traverse_graph` is unimplemented in v0

- **WHEN** an MCP client calls `opencg/traverse_graph`
- **THEN** the server returns `code = "not_implemented_in_mvp"`

### Requirement: Concept clustering for review

The system SHALL NOT maintain a concept clustering in v0. A follow-up change MUST introduce the clustering job and the admin UI surface together.

#### Scenario: No clusters are produced or queryable in v0

- **WHEN** any caller asks for clusters in v0
- **THEN** no clustering job exists and no clustering API responds
