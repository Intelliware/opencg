## Why

The knowledge graph shipped with typed *edges* and untyped *nodes*. `relationship_vocab` constrains the ten legal arrow names, but a `concept` row is just a name, a description, and an aliases array. Nothing records that `parse_config` is a **function**, that `Prompt Caching` is a **topic**, or that `checks.py` is a **module** — and nothing prevents the extractor from emitting `"Prompt Caching" calls "Anthropic API"`, which is meaningless.

That gap has three concrete costs today:

- **The extractor guesses in an unbounded space.** The prose prompt names the ten legal relations but says nothing about what kinds of things may sit on either end, so `gemma3:4b` invents edges that are locally plausible and globally nonsense. The 0.6 confidence floor is the only filter, and confidence is self-reported.
- **Review has no leverage.** A human promoting candidates one at a time is doing work a schema could have done in bulk. "Reject every `calls` edge whose source is not a code symbol" is currently not expressible.
- **Traversal cannot be narrowed by kind.** `GET /graph/traverse` filters by edge type but not by node type, so "show me the services this depends on, not the docs that mention it" is unanswerable.

An ontology layer is the missing schema. It says what kinds of things exist, how those kinds relate to each other, and which relationships are legal between which kinds. Every other pillar gets sharper the moment it exists: extraction gets constrained, review gets bulk operations, traversal gets a type filter, and retrieval gets a future join key.

## What Changes

- **New first-class entity: the ontology class.** A named kind of thing (`Function`, `Module`, `Service`, `Topic`, `Document`) with a stable `class_id`, a canonical `name`, a `description`, an optional `parent_class_id`, and a `state` reflecting whether it is part of the seeded core or operator-authored.
- **A single-parent subtype hierarchy.** Classes form a tree rooted at `Thing`. Subsumption is transitive: if `Method` is a subtype of `Function` and `Function` is a subtype of `CodeSymbol`, then a `Method` satisfies any constraint written against `CodeSymbol`. Cycles are rejected; a class may not be its own ancestor.
- **Concepts gain a class.** `opencg.concept` gains a nullable `class_id` FK. Nullable, not `NOT NULL`, because every concept extracted before this change is genuinely unclassified and pretending otherwise would be a lie in the data. Unclassified concepts sort to the top of the review queue.
- **Domain/range constraints on relationship types.** A new table declares which `(domain class, relationship type, range class)` triples are legal — `calls` runs `Function → Function`, `defined_in` runs `CodeSymbol → Module`, `depends_on` runs `Service → Service`. A relationship type with no constraint rows is unconstrained, so existing behaviour is preserved until an operator narrows it.
- **The relationship vocabulary is absorbed into the ontology.** `opencg.relationship_vocab` becomes `opencg.ontology_relationship`, and edge types are governed by the ontology's admin API, audit vocabulary, and version rather than by a surface of their own. `name` stays the primary key, so `relationship_edge.type`'s foreign key — and the guarantee that an unknown edge type fails at the database — survives the rename untouched. `/graph/vocab` stays as a deprecated alias for one release. Classes, relationship types, and constraints are one model, versioned together.
- **A seeded core ontology, extensible per deployment.** Ships with a small tree covering what openCG actually ingests today — code symbols and documents — plus the constraints for the six code relations graphifyy emits. Operators add classes and constraints through the admin API; nothing about the core is privileged at query time.
- **Type-aware extraction.** The prose extractor's prompt is rebuilt from the ontology rather than hardcoded: it names the legal classes, asks the model to classify each concept it emits, and names the legal `(domain, relation, range)` triples instead of a bare list of relation names. The code path classifies deterministically from graphifyy's `symbol_kind`, which already distinguishes `class` / `function` / `method` / `module`.
- **Constraint checking is advisory, never fatal.** An edge that violates a constraint is still written, marked `constraint_violation`, and routed to review. It is excluded from traversal by default exactly as a candidate is. Hard database rejection was rejected as an option: it would make a schema edit retroactively destroy extracted data, and it would give ingestion a new way to fail.
- **Class-filtered traversal.** `GET /graph/traverse` accepts a `classes` parameter, filtering returned nodes by class with subtype expansion.
- **Admin UI `/ontology` page.** A class-tree editor, a constraint matrix per relationship type, and a violations queue. Every ontology edit writes to the existing append-only `graph_audit_log`.

## Capabilities

### New Capabilities

- `ontology`: the class hierarchy, the relationship-type vocabulary absorbed from the knowledge graph, the domain/range constraint model, the seeded core ontology, the subsumption rules, and the admin API that governs all of it.

### Modified Capabilities

- `knowledge-graph`: `opencg.concept` gains `class_id`; `opencg.relationship_edge` gains a constraint-violation marker. The relationship vocabulary moves out to the ontology — `relationship_vocab` is renamed `ontology_relationship` and administered there, with its FK and deprecation semantics preserved. Automatic relationship extraction becomes ontology-aware — the prompt is generated from the ontology and extracted concepts carry a proposed class. Graph traversal ADDs a `classes` filter with subtype expansion.
- `admin-ui`: ADDs the `/ontology` page (class tree, constraint matrix, violations queue) and a class badge on the existing concept surfaces. Storybook coverage is required for every new component.
- `retrieval-pipeline`: ADDs the ontology admin endpoints under `/ontology/...`, including the relationship-type routes that supersede `/graph/vocab`, and extends `/graph/traverse` with the `classes` parameter. The retrieve path itself does NOT consult the ontology in this change.
- `model-providers`: no new client. The extraction call MODIFIES its prompt construction and its token accounting stays on the existing `pipeline.graph_extract` span, which grows an `ontology_version` attribute.

## Impact

- New Postgres tables in `infra/postgres/init/`: `opencg.ontology_class`, `opencg.ontology_constraint`. Both seeded at init.
- Renamed table: `opencg.relationship_vocab` becomes `opencg.ontology_relationship` and gains an `origin` column. The primary key and the `relationship_edge.type` foreign key ride along, so no edge row is rewritten.
- Altered tables: `opencg.concept` ADDs `class_id UUID NULL REFERENCES ontology_class`; `opencg.relationship_edge` ADDs `constraint_state TEXT` defaulting to `unchecked`.
- `services/pipeline` gains an `ontology/` module (class CRUD, cycle detection, subsumption resolution, constraint checking, and the relationship-type CRUD moved out of `graph/`) and `ontology/routes.py` following the pattern of `graph/routes.py`.
- `services/pipeline/src/opencg_pipeline/graph/extract.py` changes materially: the prompt becomes generated rather than literal, and the response schema gains a per-concept class.
- `services/ingestion/src/opencg_ingestion/graph_writer.py` maps graphifyy's `symbol_kind` onto core ontology classes.
- `services/admin-ui` gains the `/ontology` route plus shared components with stories.
- `packages/shared` + `packages/shared-py` gain `OntologyClass`, `OntologyRelationship`, `OntologyConstraint`, `ClassRef`, and a `ConstraintState` enum.
- New Prometheus counter: `opencg_constraint_violations_total{relation,domain_class,range_class}`.
- The explainer gains an `ontology` pillar; existing pillars 07–12 renumber to 08–13.

## Why this is one change

Splitting the class hierarchy from the constraint model would ship a taxonomy nobody can act on — classes that label things but forbid nothing and filter nothing. Splitting type-aware extraction out would ship an ontology that no data conforms to, so the violations queue would be empty and the whole layer would look inert. The unit that delivers value is "kinds exist, kinds constrain relationships, and new data is classified as it arrives."

Deliberately deferred to follow-ups so each can be measured on its own: **ontology-aware retrieval** (the retrieve path filtering or boosting by class), **RDF/OWL/SKOS import and export**, **multiple inheritance**, and **backfill classification of the existing unclassified concept corpus**.
