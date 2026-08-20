---
id: ontology
title: Ontology
capabilities: ontology
status: planned
services: pipeline, ingestion, postgres
stores: postgres
tagline: The schema the graph does not have yet — what kinds of things exist, and which relationships are legal between which kinds.
---

## What it is

**Nothing yet. This pillar is specified, not built.** Every step below describes
what `add-ontology-layer` says will happen, and each one links to the spec that
says it rather than to code, because there is no code.

The knowledge graph shipped with typed **edges** and untyped **nodes**.
`relationship_vocab` makes `type = "nonsense"` fail at the database, but a
`concept` row is only a name, a description, and an aliases array. Nothing
records that `parse_config` is a *function*, that `Prompt Caching` is a *topic*,
or that `checks.py` is a *module*.

The ontology is the missing half: a tree of **classes** saying what kinds of
things exist, and **domain/range constraints** saying which relationship types
may run between which kinds — `calls` connects a Function to a Function,
`defined_in` connects a code symbol to a module.

It also takes custody of the arrow names. The relationship vocabulary moves out
of the graph and into the ontology as `ontology_relationship`, so classes,
relationship types, and constraints are one model with one admin API, one audit
vocabulary, and one version.

## Why it exists

Without it, `"Prompt Caching" calls "Anthropic API"` is an edge the system has
no way to recognise as nonsense. The extractor is handed ten relation names and
nothing about what may sit on either end, so the only filter on a bad guess is a
confidence score the model reports about itself.

Three things get sharper the moment kinds exist. Extraction gets a bounded space
to guess in. Review gets leverage, because "reject every `calls` edge whose
source is not a code symbol" becomes one rule instead of a hundred clicks. And
traversal gets a type filter, so "the services this depends on, not the docs
that mention it" becomes answerable.

## Flow

### 1. Kinds form a tree
`Thing` at the root; `CodeSymbol`, `Document`, `Service`, and `Topic` beneath it;
`Module`, `Class`, `Function`, and `ExternalPackage` beneath `CodeSymbol`; and
`Method` beneath `Function`. Single parent only — no multiple inheritance —
because subsumption over a tree is a recursive walk anyone can read, and a DAG
would need diamond-resolution rules that nothing in the corpus asks for.
file: openspec/changes/add-ontology-layer/specs/ontology/spec.md

### 2. The arrow names move in too
`relationship_vocab` is renamed `ontology_relationship` and governed by the
ontology rather than by the graph. `name` stays the primary key, so the foreign
key that makes an unknown edge type a database error survives the rename
untouched and no edge row is rewritten. A half-schema that says what kinds of
things exist but not what kinds of arrows exist would have left an operator
editing one model through two APIs.
file: openspec/changes/add-ontology-layer/design.md

### 3. Constraints narrow, they never widen
A constraint declares one legal `(domain, relation, range)` triple. A relationship
type with no constraints accepts anything, so the day the layer lands nothing
existing becomes illegal. The seed constrains only the five relations the code
extractor emits and leaves `mentions`, `related_to`, `supersedes`, `causes`, and
`derived_from` deliberately open.
file: openspec/changes/add-ontology-layer/specs/ontology/spec.md

### 4. Subtypes inherit their ancestors' constraints
`calls` is written once as `Function → Function`. A `Method` satisfies it because
`Method` sits under `Function`. Ancestry is resolved with a recursive SQL walk
rather than a cached closure table, because the tree holds tens of rows and a
cache that must be invalidated on every edit is a correctness liability bought
for speed nobody needs.
file: openspec/changes/add-ontology-layer/design.md

### 5. The code path classifies for free
graphifyy already distinguishes `class`, `function`, `method`, and `module` — it
writes that into chunk metadata as `symbol_kind` and the graph writer currently
throws it away. Mapping it onto ontology classes costs no model call and no
tokens, and gives the graph a correctly-typed backbone to measure everything
else against.
file: services/ingestion/src/opencg_ingestion/graph_writer.py

### 6. The prose path gets a generated prompt
`extract.py`'s hardcoded relation list is replaced by a prompt rendered from the
live ontology: the class names, and the legal triples instead of bare relation
names. The model is asked to classify each concept it emits. An operator adding
a class changes the next chunk's prompt with no deploy and no code change.
file: services/pipeline/src/opencg_pipeline/graph/extract.py

### 7. Violations are recorded, never rejected
An edge that breaks a constraint is still written, marked `violation`, and hidden
from traversal the same way a candidate is. Hard rejection was considered and
refused twice over: it would give ingestion a new way to fail a chunk, and it
would turn an admin's schema edit into a destructive data operation against rows
extracted under the old schema.
file: openspec/changes/add-ontology-layer/design.md

### 8. Unclassified is a real answer
`concept.class_id` is nullable, and an edge with an unclassified endpoint stays
`unchecked` rather than becoming a violation. Every concept extracted before the
ontology existed is genuinely of unknown kind; defaulting it to the root class
would store a lie that no query could tell apart from a deliberate choice.
file: openspec/changes/add-ontology-layer/specs/knowledge-graph/spec.md

### 9. Editing the schema re-checks, it does not rewrite
Adding or removing a constraint marks the affected edges `unchecked` and
re-evaluates them. It never touches an edge's `state`. The two axes stay
independent on purpose: `state` is what a human decided, `constraint_state` is
what the schema says.
file: openspec/changes/add-ontology-layer/specs/ontology/spec.md

### 10. Review in the admin UI
A planned `/ontology` page holds three surfaces: the class tree, a constraint
matrix per relationship type, and a violations queue. The queue offers
"reclassify endpoint" alongside promote and reject, because a violation is as
often a mis-typed node as a wrong edge.
file: openspec/changes/add-ontology-layer/specs/admin-ui/spec.md

## Facts
- Status: **specified, not implemented** — `add-ontology-layer`, 0 of 83 tasks done
- Planned tables: `opencg.ontology_class`, `opencg.ontology_constraint`
- Renamed table: `relationship_vocab` becomes `opencg.ontology_relationship`, keeping its primary key and its edge foreign key
- Planned columns: `concept.class_id` (nullable), `relationship_edge.constraint_state`
- **10** seeded classes; **7** seeded constraints covering 5 of the 10 relation types
- Constraint verdicts: `unchecked`, `ok`, `violation` — advisory, never enforced
- Subsumption: recursive CTE over `parent_class_id`, no closure table
- Planned counter: `opencg_constraint_violations_total{relation,domain_class,range_class}`

## Gaps
- **None of this exists.** The change is written and validated; no table, route, or component has been built. Everything above is the design, not the system.
- **Retrieval will not consult the ontology.** Same deliberate deferral as the graph itself: `/retrieve` stays pure hybrid text search so the layer's impact can be measured on its own.
- **`/graph/vocab` survives as a deprecated alias** for one release after the vocabulary moves. Two paths answer the same question until the follow-up removes the old one.
- **No RDF, OWL, or SKOS.** No triple store, no reasoner, no importing an external ontology. Domain and range only — no cardinality, disjointness, or transitivity axioms.
- **No multiple inheritance.** A class has exactly one parent.
- **The existing corpus stays unclassified.** Nothing in this change backfills concepts extracted before it; how that happens is an open question.
- **Classification quality is unmeasured.** There is no labelled set, so how well `gemma3:4b` assigns kinds is currently unknowable. The violations queue is the first instrument that would say.
