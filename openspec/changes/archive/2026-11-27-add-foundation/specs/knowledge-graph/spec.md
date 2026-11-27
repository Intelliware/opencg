## ADDED Requirements

### Requirement: Named relationship types

The graph schema SHALL represent concept-to-concept relationships as **named edges** drawn from a curated, extensible vocabulary (e.g., `depends_on`, `defined_in`, `supersedes`, `mentions`, `owned_by`, `relates_to`). The vocabulary SHALL be editable through an admin API; relationship names SHALL be unique and human-readable.

#### Scenario: Vocabulary lookup

- **WHEN** the system creates an edge
- **THEN** the edge `type` is a name present in the relationship vocabulary table
- **AND** an attempted insert with an unknown name is rejected with a `relationship_unknown` error

#### Scenario: Admin adds a new relationship type

- **WHEN** an admin posts `{ name: "compatible_with", description: "...", inverse: "compatible_with", directed: false }` to the vocabulary API
- **THEN** subsequent inserts using `compatible_with` are accepted

### Requirement: Automatic relationship extraction

During ingestion and background enrichment, the system SHALL extract candidate relationships from new and changed content using a configurable extractor (model-backed). Extracted edges SHALL be persisted in a `candidate` state with `confidence`, `evidence_uri`, and `extractor_version`. They SHALL NOT participate in retrieval until promoted.

#### Scenario: Extractor finds a candidate edge

- **WHEN** a document mentions "Service A depends on Service B"
- **THEN** the extractor inserts a candidate edge `(Service A) -[depends_on { state:"candidate", confidence:0.82 }]-> (Service B)`
- **AND** the candidate edge does not appear in `traverse_graph` responses

### Requirement: Review, promote, edit, and delete

Admins SHALL be able to list candidate edges, promote them to `confirmed`, edit their type or endpoints, or delete them. Every state transition SHALL be recorded with actor, timestamp, and reason.

#### Scenario: Admin promotes a candidate

- **WHEN** an admin promotes a candidate edge via the admin API
- **THEN** the edge state becomes `confirmed`
- **AND** an audit row records `actor`, `from_state`, `to_state`, `reason`, `at`
- **AND** subsequent `traverse_graph` calls include the edge

### Requirement: Graph traversal API

The system SHALL expose a `traverse_graph` capability that takes a starting entity ID, an optional list of allowed relationship types, a max depth, and a result limit, and returns the reachable subgraph.

#### Scenario: Bounded traversal

- **WHEN** a caller requests traversal from entity `E1` with `types = ["depends_on"]`, `depth = 2`, `limit = 50`
- **THEN** the response contains at most 50 nodes reachable via up-to-two `depends_on` hops from `E1`
- **AND** confirmed edges only — candidate edges are excluded by default

### Requirement: Concept clustering for review

The system SHALL maintain a periodically refreshed clustering of entities (e.g., community detection over confirmed edges) and expose it to the admin UI so reviewers can browse conceptually related groups when editing relationships.

#### Scenario: Cluster view available

- **WHEN** the admin UI requests clusters
- **THEN** the system returns a list of clusters with `id`, `label`, `member_count`, and a sampling of representative members
