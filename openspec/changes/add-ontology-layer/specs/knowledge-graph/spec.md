## MODIFIED Requirements

### Requirement: Named relationship vocabulary

The graph schema SHALL represent concept-to-concept relationships as **named edges** drawn from a curated, extensible vocabulary. That vocabulary is now part of the ontology: it lives in `opencg.ontology_relationship`, renamed from `opencg.relationship_vocab`. Rows SHALL include `name` (primary key), `description`, `inverse` (optional name of the inverse relation), `directed` (boolean, default true), `deprecated_at` (nullable timestamp), and `origin` (one of `core`, `operator`). The vocabulary MUST be seeded at DB init with at least: `depends_on`, `defined_in`, `supersedes`, `mentions`, `related_to`, `causes`, `derived_from`.

The deterministic code extractor also requires the seeded names `calls`, `imports`, and `uses`, for a total of ten default vocabulary entries.

Edges in `opencg.relationship_edge` SHALL carry a `type TEXT` column with a FK to `ontology_relationship.name`. Inserts with an unknown name MUST fail at the database level. The rename MUST preserve this foreign key rather than dropping and recreating it, so the guarantee holds continuously across the migration.

The vocabulary MUST be editable through the **ontology** admin API — add a row, edit `description` / `inverse` / `directed`, mark a row deprecated — rather than through a vocabulary API of its own. Marking a row deprecated MUST NOT delete it nor cascade to existing edges.

#### Scenario: Vocabulary FK rejects unknown names

- **WHEN** any caller attempts to insert into `opencg.relationship_edge` with `type = "nonsense"`
- **THEN** the insert fails with a foreign key violation

#### Scenario: Vocabulary seeded at init

- **WHEN** the database first starts under this change
- **THEN** `ontology_relationship` contains the ten seeded semantic and code relationship names with `deprecated_at IS NULL`
- **AND** every one of them carries `origin = "core"`

#### Scenario: Admin adds a new relationship type

- **WHEN** an admin posts `{name:"compatible_with", description:"…", inverse:"compatible_with", directed:false}` to the ontology relationships endpoint
- **THEN** subsequent inserts using `compatible_with` are accepted
- **AND** the new row carries `origin = "operator"`

#### Scenario: Deprecation preserves existing edges

- **WHEN** an admin deprecates the `causes` vocabulary row
- **THEN** existing edges with `type = "causes"` continue to traverse normally
- **AND** new edge inserts with `type = "causes"` are rejected with a `vocab_deprecated` error

### Requirement: Concept identity and lifecycle

The system SHALL maintain a `opencg.concept` table with `concept_id UUID PRIMARY KEY`, `tenant TEXT NOT NULL`, `name TEXT NOT NULL`, `dedupe_key TEXT NOT NULL`, `description TEXT`, `aliases TEXT[] NOT NULL DEFAULT '{}'`, `class_id UUID NULL REFERENCES opencg.ontology_class(class_id)`, `state TEXT NOT NULL DEFAULT 'candidate'`, `confidence FLOAT`, `extractor_version TEXT`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`, `tombstoned_at TIMESTAMPTZ`. A UNIQUE constraint on `(tenant, dedupe_key)` enforces dedupe.

The `dedupe_key` MUST be computed as `lower(unaccent(regexp_replace(trim(name), '\s+', ' ', 'g')))` so visually-equivalent surface forms collide.

`class_id` SHALL be nullable. A null value means no extractor or operator has yet stated what kind of thing the concept is, and MUST be distinguishable from a deliberate classification as the root class `Thing`. Concepts with `class_id IS NULL` SHALL be listable through the admin API so the unclassified backlog is directly queryable.

Reclassifying a concept — setting or changing `class_id` — MUST write a `graph_audit_log` row with `target_kind = "concept"` and before/after snapshots, and MUST NOT alter the concept's `state`.

#### Scenario: Dedupe key catches case and whitespace variants

- **WHEN** the extractor inserts `name = "Prompt Caching"` and later `name = " PROMPT  CACHING "`
- **THEN** the second insert collides on `(tenant, dedupe_key)` and the existing concept is reused
- **AND** the new surface form is appended to `aliases` if it is not already present

#### Scenario: Tombstoned concepts are excluded from browse

- **WHEN** an admin tombstones a concept
- **THEN** `GET /graph/concepts` excludes it by default
- **AND** the concept can be re-included by passing `include_tombstoned=true`

#### Scenario: Concepts predating the ontology remain unclassified

- **WHEN** the ontology migration completes against a database holding concepts written before this change
- **THEN** those concepts have `class_id IS NULL`
- **AND** none of them is silently assigned the root class

#### Scenario: The unclassified backlog is queryable

- **WHEN** an admin lists concepts filtered to unclassified
- **THEN** the response contains exactly the concepts with `class_id IS NULL`

#### Scenario: Reclassification is audited and leaves review state alone

- **WHEN** an operator changes a `confirmed` concept's `class_id` from `Topic` to `Service`
- **THEN** the concept's `state` remains `confirmed`
- **AND** a `graph_audit_log` row records the previous and new `class_id`

### Requirement: Automatic relationship extraction

Ingestion SHALL run a *concept-and-relationship extractor* on every chunk after the chunk's vector point is upserted to Qdrant. The extractor MUST call a chat model (default: Ollama Cloud `gemma3:4b`) and request a structured JSON output containing `concepts` and `relations`. Concepts MUST be deduped against `opencg.concept` by a normalised `dedupe_key` (Unicode-folded, case-folded, whitespace-collapsed). New concepts AND new edges land in `state = "candidate"`.

The extractor's prompt SHALL be generated from the live ontology rather than embedded as a literal. The generated prompt MUST name the available classes with their descriptions and MUST express the legal relationships as `(domain class, relation, range class)` triples rather than as a bare list of relation names. Relationship types with no constraints MUST be presented as accepting any endpoints.

The extractor MUST request a proposed class for every concept it emits. A proposed class that does not resolve to a known, non-deprecated ontology class MUST be discarded, leaving that concept's `class_id` null; it MUST NOT fail the chunk.

Prompt generation MUST be bounded by a configured character budget. When the rendered ontology exceeds it, class definitions MUST be retained in full and constraint triples truncated, with the truncation stated in the prompt.

The extractor MUST be best-effort: a failure (timeout, parse error, model unavailable) on one chunk MUST NOT fail the ingest. Failures MUST increment `opencg_extractor_errors_total{reason}` and log a structured warning naming the chunk's `entity_id`.

Every extracted edge MUST carry a `confidence FLOAT`, an `evidence_uri TEXT` pointing at the source chunk's `entity_id`, and an `extractor_version TEXT`. Edges below a configurable `min_confidence` (default 0.6) MUST NOT be inserted at all.

#### Scenario: Extractor finds two new concepts and an edge in a chunk

- **WHEN** a newly upserted chunk's text mentions "Service A depends on Service B"
- **THEN** two `candidate` concept rows are created with `name` = `Service A` / `Service B` and normalised `dedupe_key`s
- **AND** a `candidate` edge is created with `type = "depends_on"`, `evidence_uri` referencing the chunk, and `confidence ≥ 0.6`

#### Scenario: Extractor reuses an existing concept

- **WHEN** a chunk mentions "Prompt Caching" and a concept with `dedupe_key = "prompt caching"` already exists
- **THEN** no new concept is created
- **AND** any new edge refers to the existing concept's `concept_id`

#### Scenario: Extractor failure does not fail the ingest

- **WHEN** the chat model is unreachable during a chunk's extraction pass
- **THEN** the chunk's catalog row and Qdrant point are still upserted
- **AND** `opencg_extractor_errors_total{reason}` increments
- **AND** no concept or edge rows are written for that chunk

#### Scenario: Edges below the confidence threshold are dropped

- **WHEN** the extractor returns an edge with `confidence = 0.3` and the configured `min_confidence` is `0.6`
- **THEN** no edge row is written for that triple

#### Scenario: An operator's new class reaches the prompt without a code change

- **WHEN** an operator adds a class through the ontology admin API and a chunk is extracted afterwards
- **THEN** the prompt sent to the chat model names the new class
- **AND** no deployment or code change was required

#### Scenario: An unknown proposed class is discarded, not fatal

- **WHEN** the model returns a concept whose proposed class matches no ontology class
- **THEN** the concept is still written
- **AND** its `class_id` is null
- **AND** the chunk's extraction otherwise completes normally

#### Scenario: Oversized ontology is truncated at the constraints

- **WHEN** the rendered ontology exceeds the configured prompt character budget
- **THEN** every class definition is still present in the prompt
- **AND** the constraint list is truncated with the truncation stated in the prompt

### Requirement: Graph traversal API

The system SHALL expose `GET /graph/traverse?concept_id=…&types=…&classes=…&depth=…&limit=…&include_candidates=…&include_violations=…` returning the reachable subgraph as `{nodes: [...], edges: [...]}`. `depth` defaults to `2` and is capped at `4`. `limit` defaults to `50` and is capped at `200`. `types` accepts a comma-separated list of vocabulary names; absence means "all types". `include_candidates` defaults to `false`; when `true`, candidate edges and their endpoints are included.

`classes` accepts a comma-separated list of ontology class names; absence means "all classes". A named class SHALL match concepts of that class **and of every descendant class**. Concepts with `class_id IS NULL` MUST NOT match any `classes` filter, and MUST be returned when no filter is supplied.

`include_violations` defaults to `false`; when `false`, edges with `constraint_state = "violation"` MUST be omitted. Every returned node MUST carry its `class_id` and class name where one is set; every returned edge MUST carry its `constraint_state`.

The endpoint MUST execute the traversal via Apache AGE (openCypher) against the `opencg` graph, then hydrate node rows from `opencg.concept` so `name`, `description`, `state`, and class information are present.

#### Scenario: Bounded depth traversal

- **WHEN** a caller calls traverse with `concept_id = C1`, `depth = 2`, `types = "depends_on"`, `limit = 50`
- **THEN** the response contains at most 50 nodes reachable via up to two `depends_on` hops from `C1`
- **AND** confirmed edges only — candidate edges are not present

#### Scenario: Include candidates flag

- **WHEN** the same caller passes `include_candidates = true`
- **THEN** candidate edges and the candidate concepts they connect to are included
- **AND** each node and edge in the response carries its `state` field

#### Scenario: Cap enforcement

- **WHEN** a caller passes `depth = 10`
- **THEN** the request is rejected with `400 Bad Request` and an error message naming the depth cap

#### Scenario: Class filter expands to subtypes

- **WHEN** a caller passes `classes = "CodeSymbol"` and the reachable set holds concepts classified `Module`, `Method`, and `Topic`
- **THEN** the `Module` and `Method` concepts are returned
- **AND** the `Topic` concept is not

#### Scenario: Unclassified concepts are excluded by a class filter

- **WHEN** a caller passes any `classes` value and a reachable concept has `class_id IS NULL`
- **THEN** that concept is absent from the response

#### Scenario: Violations are omitted unless requested

- **WHEN** a caller traverses without `include_violations`
- **THEN** no edge with `constraint_state = "violation"` appears in the response
- **AND** passing `include_violations = true` includes them, each carrying its `constraint_state`

#### Scenario: Unknown class name is rejected

- **WHEN** a caller passes `classes = "Nonsense"` and no such ontology class exists
- **THEN** the request is rejected with `400 Bad Request` naming the unknown class

## ADDED Requirements

### Requirement: Deterministic classification of code-extracted concepts

The `graph_writer` module SHALL classify every concept it writes from a graphifyy extraction, without calling any chat model, by mapping graphifyy's `symbol_kind` onto core ontology classes: `module → Module`, `class → Class`, `function → Function`, `method → Method`. Concepts created on the fly for external import targets SHALL be classified `ExternalPackage`.

A `symbol_kind` outside that map MUST leave `class_id` null and log at debug level; it MUST NOT fail the write. Because these classifications derive from parsing rather than inference, they carry the same `confirmed` state and provenance the writer already assigns to code-extracted rows.

#### Scenario: Symbol kinds map onto core classes

- **WHEN** the writer persists concepts for a Python file holding a module, a class, a function, and a method
- **THEN** each concept's `class_id` resolves to `Module`, `Class`, `Function`, and `Method` respectively
- **AND** no chat-model call is made

#### Scenario: External import target is classified

- **WHEN** the writer creates a concept on the fly for the target of `imports os`
- **THEN** the concept's `class_id` resolves to `ExternalPackage`

#### Scenario: Unmapped symbol kind leaves the concept unclassified

- **WHEN** graphifyy emits a symbol whose kind is outside the map
- **THEN** the concept row is still written with `class_id IS NULL`
- **AND** the surrounding extraction completes

#### Scenario: Code-classified concepts give the violations queue a baseline

- **WHEN** a prose-extracted `calls` edge points at a concept the code path classified `Module`, and `calls` is constrained to `Function → Function`
- **THEN** the edge's `constraint_state` is `violation`
