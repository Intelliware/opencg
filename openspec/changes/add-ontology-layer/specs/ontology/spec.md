## ADDED Requirements

### Requirement: Ontology class identity and hierarchy

The system SHALL maintain an `opencg.ontology_class` table with `class_id UUID PRIMARY KEY`, `name TEXT NOT NULL`, `dedupe_key TEXT NOT NULL`, `description TEXT`, `parent_class_id UUID NULL REFERENCES opencg.ontology_class(class_id)`, `origin TEXT NOT NULL` (one of `core`, `operator`), `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`, and `deprecated_at TIMESTAMPTZ`. A UNIQUE constraint on `dedupe_key` enforces name uniqueness under the same normalisation already used by `opencg.concept` (Unicode-folded, case-folded, whitespace-collapsed).

Classes SHALL form a single-parent tree. Exactly one class — the seeded root `Thing` — has `parent_class_id IS NULL`; every other class MUST name a parent.

#### Scenario: Root class has no parent

- **WHEN** the database first starts under this change
- **THEN** exactly one `ontology_class` row has `parent_class_id IS NULL`
- **AND** that row's `name` is `Thing`

#### Scenario: Class names are unique under normalisation

- **WHEN** an operator creates a class named `Code Symbol` and a class named `code  symbol` already exists
- **THEN** the second insert is rejected on the `dedupe_key` unique constraint
- **AND** the response names the existing class

#### Scenario: A non-root class requires a parent

- **WHEN** an operator posts a new class with no `parent_class_id`
- **THEN** the request is rejected with `400 Bad Request`
- **AND** the error states that only the root class may be parentless

### Requirement: Cycle rejection on reparenting

The system SHALL reject any class insert or update whose `parent_class_id` would make the class its own ancestor. The check MUST walk the ancestor chain before the write commits, and MUST treat a self-reference (`parent_class_id = class_id`) as a cycle.

#### Scenario: Direct self-parent is rejected

- **WHEN** an operator patches class `Function` to set `parent_class_id` to `Function`'s own `class_id`
- **THEN** the request is rejected with `400 Bad Request`
- **AND** no row is modified

#### Scenario: Indirect cycle is rejected

- **WHEN** `Method`'s parent is `Function` and `Function`'s parent is `CodeSymbol`, and an operator patches `CodeSymbol` to set its parent to `Method`
- **THEN** the request is rejected with `400 Bad Request` naming the cycle
- **AND** `CodeSymbol` retains its original parent

#### Scenario: Legal reparent succeeds

- **WHEN** an operator moves an operator-authored class to a different parent that is not among its descendants
- **THEN** the update succeeds
- **AND** subsequent subsumption queries reflect the new ancestry without any further action

### Requirement: Subtype subsumption

The system SHALL treat a class as satisfying any requirement written against any of its ancestors. Ancestor and descendant sets MUST be computed by recursive traversal of `parent_class_id` at query time; the system MUST NOT depend on a materialised closure table that could drift from the class tree.

Subsumption applies wherever a class is compared: constraint evaluation and class-filtered traversal both expand a named class to that class plus all of its descendants.

#### Scenario: A subtype satisfies an ancestor's constraint

- **WHEN** a constraint declares `calls` runs `Function → Function`, and an edge runs from a concept classified `Method` to a concept classified `Function`, where `Method`'s parent is `Function`
- **THEN** the edge evaluates to `constraint_state = "ok"`

#### Scenario: Ancestry is transitive across more than one hop

- **WHEN** a constraint names `CodeSymbol` and a concept is classified `Method`, whose ancestry is `Method → Function → CodeSymbol → Thing`
- **THEN** the concept satisfies the constraint

#### Scenario: An unrelated class does not satisfy a constraint

- **WHEN** a constraint declares `calls` runs `Function → Function` and an edge's source concept is classified `Topic`
- **THEN** the edge does not satisfy the constraint

### Requirement: Relationship types are ontology objects

The relationship vocabulary SHALL become part of the ontology. `opencg.relationship_vocab` is renamed `opencg.ontology_relationship`, retaining `name TEXT PRIMARY KEY`, `description`, `inverse`, `directed`, and `deprecated_at`, and gaining `origin TEXT NOT NULL` (one of `core`, `operator`) backfilled to `core` for the ten seeded rows.

Because `name` remains the primary key, the existing `opencg.relationship_edge.type` foreign key MUST survive the rename unchanged. Inserting an edge whose `type` names no relationship row MUST still fail at the database level, and no edge row may be rewritten by this migration.

The existing deprecation semantics carry over verbatim: deprecating a relationship type MUST NOT delete it and MUST NOT cascade to existing edges, existing edges of that type MUST continue to traverse normally, and new edge inserts naming it MUST be rejected with a `vocab_deprecated` error.

Classes, relationship types, and constraints together SHALL constitute the ontology for the purposes of versioning, so a single `ontology_version` covers an edit to any of the three.

#### Scenario: Renamed table keeps rejecting unknown edge types

- **WHEN** any caller attempts to insert into `opencg.relationship_edge` with `type = "nonsense"` after the migration
- **THEN** the insert fails with a foreign key violation

#### Scenario: Migration preserves existing vocabulary and edges

- **WHEN** the rename runs against a database holding the ten seeded relationship types and edges referencing them
- **THEN** all ten rows are present in `ontology_relationship` with `origin = "core"`
- **AND** every existing edge retains its `type` and its referential integrity
- **AND** no edge row is modified by the migration

#### Scenario: Deprecating a relationship type still preserves its edges

- **WHEN** an operator deprecates the `causes` relationship type through the ontology API
- **THEN** existing edges with `type = "causes"` continue to traverse normally
- **AND** new edge inserts with `type = "causes"` are rejected with a `vocab_deprecated` error

#### Scenario: A relationship edit bumps the ontology version

- **WHEN** an operator adds a relationship type
- **THEN** the `ontology_version` reported to extraction changes, exactly as it would for a class or constraint edit

### Requirement: Domain and range constraints

The system SHALL maintain an `opencg.ontology_constraint` table with `constraint_id UUID PRIMARY KEY`, `relationship_type TEXT NOT NULL REFERENCES opencg.ontology_relationship(name)`, `domain_class_id UUID NOT NULL REFERENCES opencg.ontology_class(class_id)`, `range_class_id UUID NOT NULL REFERENCES opencg.ontology_class(class_id)`, `origin TEXT NOT NULL` (one of `core`, `operator`), and `created_at TIMESTAMPTZ`. A UNIQUE constraint on `(relationship_type, domain_class_id, range_class_id)` prevents duplicates.

Domain and range SHALL remain rows in this table rather than columns on `ontology_relationship`, because a relationship type carries many legal triples evaluated disjunctively.

Multiple constraint rows for one `relationship_type` SHALL be evaluated as a disjunction: an edge satisfies the relationship type if it satisfies **any** one of that type's constraint rows.

#### Scenario: Disjunctive constraints on one relationship type

- **WHEN** `imports` carries two constraints, `Module → Module` and `Module → ExternalPackage`, and an edge runs `Module → ExternalPackage`
- **THEN** the edge evaluates to `constraint_state = "ok"`

#### Scenario: Duplicate constraint rejected

- **WHEN** an operator posts a constraint identical to an existing `(relationship_type, domain_class_id, range_class_id)` triple
- **THEN** the request is rejected with `409 Conflict`

#### Scenario: Constraint against an unknown relationship type is rejected

- **WHEN** an operator posts a constraint whose `relationship_type` is not present in `ontology_relationship`
- **THEN** the insert fails with a foreign key violation

### Requirement: Absence of constraints means unconstrained

A relationship type with zero rows in `opencg.ontology_constraint` SHALL accept any domain class and any range class. Constraints narrow what is legal; they never widen it, and the absence of a constraint MUST NOT be read as "nothing is legal".

The seeded core SHALL leave `mentions`, `related_to`, `supersedes`, `causes`, and `derived_from` unconstrained.

#### Scenario: An unconstrained relationship type accepts any endpoints

- **WHEN** an edge of type `mentions` runs from a `Topic` to a `Module` and `mentions` has no constraint rows
- **THEN** the edge evaluates to `constraint_state = "ok"`

#### Scenario: Existing edges are not invalidated by this change landing

- **WHEN** the migration completes on a database holding edges written before this change
- **THEN** no edge is marked `violation` solely because the ontology now exists
- **AND** edges whose relationship type has no constraint rows evaluate to `ok`

### Requirement: Constraint evaluation is advisory

Constraint evaluation SHALL record its verdict on `opencg.relationship_edge.constraint_state`, whose value is one of `unchecked`, `ok`, or `violation`. Evaluation MUST NOT reject an insert, MUST NOT raise, and MUST NOT alter the edge's `state` (`candidate` / `confirmed` / `tombstoned`).

An edge whose source or target concept has `class_id IS NULL` cannot be evaluated and MUST remain `unchecked`. An unclassified endpoint MUST NOT be recorded as a violation.

Edges with `constraint_state = "violation"` MUST be excluded from traversal responses by default, on the same terms as candidate edges, and MUST be included when the caller explicitly asks for them.

#### Scenario: A violating edge is written, not rejected

- **WHEN** the extractor emits an edge of type `calls` from a concept classified `Topic` to a concept classified `Service`, and `calls` is constrained to `Function → Function`
- **THEN** the edge row is written
- **AND** its `constraint_state` is `violation`
- **AND** `opencg_constraint_violations_total{relation,domain_class,range_class}` increments

#### Scenario: An unclassified endpoint leaves the edge unchecked

- **WHEN** an edge's source concept has `class_id IS NULL`
- **THEN** the edge's `constraint_state` is `unchecked`
- **AND** the edge is not counted as a violation

#### Scenario: Violations are hidden from traversal by default

- **WHEN** a caller requests `GET /graph/traverse` without asking for violations
- **THEN** edges with `constraint_state = "violation"` are absent from the response

#### Scenario: Constraint state does not disturb human review state

- **WHEN** an edge previously promoted to `confirmed` is re-evaluated and found to violate a newly-added constraint
- **THEN** the edge's `state` remains `confirmed`
- **AND** only its `constraint_state` changes to `violation`

### Requirement: Seeded core ontology

The database SHALL seed a core class tree at init, in a script ordered after `040_graph.sql` and `050_graph_audit.sql` and before `090_grants.sql`, containing at least: `Thing` (root); `CodeSymbol`, `Document`, `Service`, and `Topic` as children of `Thing`; `Module`, `Class`, `Function`, and `ExternalPackage` as children of `CodeSymbol`; and `Method` as a child of `Function`. Every seeded row carries `origin = "core"`.

The seed SHALL also create constraints covering the relationship types the deterministic code extractor emits: `calls` (`Function → Function`), `imports` (`Module → Module` and `Module → ExternalPackage`), `defined_in` (`CodeSymbol → Module` and `CodeSymbol → Class`), `uses` (`CodeSymbol → CodeSymbol`), and `depends_on` (`Service → Service`).

Core rows SHALL carry no privilege at query time: an operator MAY deprecate a core class or delete a core constraint through the same admin API that governs operator-authored rows.

#### Scenario: Core tree present at init

- **WHEN** the database first starts under this change
- **THEN** `ontology_class` contains the ten seeded classes with `origin = "core"` and `deprecated_at IS NULL`
- **AND** `Method`'s ancestry resolves to `Function → CodeSymbol → Thing`

#### Scenario: Core constraints present at init

- **WHEN** the database first starts under this change
- **THEN** `ontology_constraint` contains the seven seeded rows
- **AND** `mentions`, `related_to`, `supersedes`, `causes`, and `derived_from` have zero constraint rows

#### Scenario: Operator may deprecate a core class

- **WHEN** an operator deprecates the core class `Service`
- **THEN** the row's `deprecated_at` is set
- **AND** concepts already classified `Service` retain their `class_id`
- **AND** new classification requests naming `Service` are rejected

### Requirement: Ontology admin API

The pipeline SHALL expose CRUD endpoints for the ontology: list and read classes (`GET /ontology/classes`, `GET /ontology/classes/{id}`), create, update, and deprecate a class; list, create, and delete constraints (`GET /ontology/constraints`, `POST /ontology/constraints`, `DELETE /ontology/constraints/{id}`); and list, create, update, and deprecate relationship types (`GET /ontology/relationships`, `POST /ontology/relationships`, `PATCH /ontology/relationships/{name}`, `DELETE /ontology/relationships/{name}` for deprecation).

`/ontology/relationships` SHALL be the canonical surface for the vocabulary previously administered at `/graph/vocab`. The `/graph/vocab` routes MUST continue to work as a deprecated alias for one release so existing local tooling does not break, and MUST be documented as deprecated.

The class list endpoint MUST be able to return the tree shape, so a caller can render the hierarchy without issuing one request per node.

Deprecating a class MUST NOT delete it, MUST NOT cascade to concepts already classified with it, and MUST NOT delete its constraint rows.

#### Scenario: Class list returns the hierarchy in one call

- **WHEN** a caller requests `GET /ontology/classes`
- **THEN** the response conveys each class's parent so the full tree can be reconstructed without further requests

#### Scenario: Deprecation preserves classified concepts

- **WHEN** an operator deprecates a class that 40 concepts are classified with
- **THEN** all 40 concepts retain that `class_id`
- **AND** the class remains readable through `GET /ontology/classes/{id}`

#### Scenario: Deleting a constraint is permitted

- **WHEN** an operator deletes a seeded constraint
- **THEN** the constraint row is removed
- **AND** edges previously marked `violation` under it are re-evaluated per the re-check requirement

#### Scenario: The deprecated vocabulary alias still answers

- **WHEN** a caller requests the vocabulary through the legacy `/graph/vocab` path
- **THEN** the response matches what `/ontology/relationships` returns
- **AND** the response marks the path as deprecated

### Requirement: Ontology edits are audited

Every ontology write — class create, class update, class deprecate, constraint create, constraint delete, and relationship-type create, update, or deprecate — SHALL append a row to the existing `opencg.graph_audit_log`, whose `target_kind` set is extended to include `ontology_class`, `ontology_constraint`, and `ontology_relationship`. Rows MUST capture `actor`, `target_id`, `target_kind`, `reason`, `at`, and JSONB `before` / `after` snapshots, and MUST obey the table's existing append-only trigger.

Rows written before this change carry `target_kind = "vocab"` for vocabulary edits. Because the log forbids `UPDATE`, those rows MUST NOT be rewritten to the new spelling; readers MUST accept both values and treat `vocab` as the pre-absorption spelling of `ontology_relationship`.

#### Scenario: Class reparent is audited with before and after

- **WHEN** an operator changes a class's parent
- **THEN** a `graph_audit_log` row is written with `target_kind = "ontology_class"`
- **AND** the `before` snapshot holds the previous `parent_class_id` and the `after` snapshot holds the new one

#### Scenario: Ontology audit rows are immutable

- **WHEN** any code path attempts to `UPDATE` or `DELETE` a `graph_audit_log` row describing an ontology edit
- **THEN** the database raises an error and the operation fails

#### Scenario: Pre-absorption audit rows keep their original target kind

- **WHEN** an operator reads the audit history of a relationship type that was edited before this change
- **THEN** the older rows still read `target_kind = "vocab"`
- **AND** they are presented alongside newer `ontology_relationship` rows as one history

### Requirement: Constraint edits schedule a re-check

Adding, editing, or deleting a constraint SHALL set `constraint_state = "unchecked"` on every edge of the affected `relationship_type` and enqueue a re-evaluation that recomputes `ok` or `violation`. The re-check MUST NOT modify any edge's `state`, and MUST NOT delete any edge.

Re-evaluation MUST be idempotent: running it twice against an unchanged ontology and an unchanged edge set produces identical `constraint_state` values.

#### Scenario: Narrowing a constraint surfaces newly-suspect edges

- **WHEN** an operator adds the first constraint to the previously-unconstrained `related_to` type
- **THEN** every `related_to` edge is marked `unchecked` and then re-evaluated
- **AND** edges that do not satisfy the new constraint become `violation`
- **AND** no `related_to` edge is deleted or demoted

#### Scenario: Deleting the last constraint clears violations

- **WHEN** an operator deletes the only constraint on a relationship type
- **THEN** edges of that type re-evaluate to `ok`

#### Scenario: Re-check is idempotent

- **WHEN** re-evaluation runs twice with no intervening ontology or edge change
- **THEN** the second run produces the same `constraint_state` for every edge as the first
