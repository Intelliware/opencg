## Context

`add-knowledge-graph` and `adopt-graphifyy` shipped a graph whose edges are typed and whose nodes are not. `opencg.relationship_vocab` holds ten legal relation names behind a foreign key, so `type = "nonsense"` fails at the database. There is no equivalent for the things the arrows connect: `opencg.concept` carries `name`, `dedupe_key`, `description`, `aliases`, `state`, and `confidence`, and that is all.

Two extractors write into that table. The code path (graphifyy) already *knows* the kind of everything it emits — it distinguishes `class`, `function`, `method`, and `module`, and it writes that into chunk metadata as `symbol_kind` — but the knowledge is discarded before it reaches `concept`. The prose path (`gemma3:4b`) is handed a bare list of ten relation names and asked for `{concepts, relations}` JSON, with nothing constraining what may sit on either end of a relation.

This change introduces the schema layer both extractors should have been writing against, and does it without invalidating a single row already in the database.

## Goals / Non-Goals

**Goals:**

- A named, hierarchical set of concept classes that operators can extend, seeded with a core that covers what openCG actually ingests today.
- Domain/range constraints that make `"Prompt Caching" calls "Anthropic API"` a *detectable* error rather than a plausible-looking edge.
- Ontology-aware extraction: the model is told which kinds exist and which triples are legal, instead of being told only which relation names exist.
- Preservation of every existing concept and edge, with no retroactive deletion when an operator narrows the schema.
- Class-filtered traversal with correct subtype semantics.

**Non-Goals:**

- **Ontology-aware retrieval.** `/retrieve` stays pure hybrid text search. Same reasoning that deferred graph-aware retrieval: measure one thing at a time.
- **RDF / OWL / SKOS interoperability.** No triple store, no reasoner, no `owl:sameAs`. Deferred until someone asks to import an external ontology.
- **Multiple inheritance.** See D1.
- **Backfill of the existing unclassified corpus.** New and re-extracted content gets classified; the existing corpus stays `class_id IS NULL` until a follow-up. See OQ3.
- **Cardinality, disjointness, or transitivity axioms.** Domain and range only. Richer axioms are unbounded scope and, without a reasoner, mostly unenforceable.

## Decisions

### D1. Single-parent tree, not a multiple-inheritance DAG

**Choice:** `ontology_class.parent_class_id` is a single nullable self-FK. Exactly one class (`Thing`) has a null parent. Cycles are rejected at write time by walking ancestors before insert or update.

**Rationale:** Subsumption over a tree is a recursive CTE that any reader of the code can follow. Over a DAG it needs a real closure computation, ambiguous-inheritance rules, and a diamond-resolution policy. Nothing in the seeded core wants two parents, and the cost of adopting a DAG later is a nullable column becoming a join table — a migration, not a redesign.

**Alternatives considered:**

- *Multiple inheritance DAG.* Rejected as unearned complexity; no concrete use case in the current corpus.
- *Flat class list, no hierarchy.* Rejected because constraints become quadratic to author. `defined_in` runs `CodeSymbol → Module`; without subsumption an operator writes that constraint once per code symbol kind and re-authors it every time a kind is added.

### D2. Constraint violations are advisory, never fatal

**Choice:** An edge violating a domain/range constraint is written to `relationship_edge` with `constraint_state = 'violation'`. It is excluded from traversal by default, exactly as a `candidate` is, and surfaced in a violations queue for review. The database does not reject it.

**Rationale:** Two hard requirements collide with enforcement. First, ingest-time extraction is best-effort by project rule — a constraint check that raises gives ingestion a brand-new way to fail on a chunk. Second, constraints are *editable at runtime*. If enforcement were an FK or a trigger, narrowing a constraint would either fail against existing rows or silently orphan them; either way an admin's schema edit becomes a destructive data operation. Recording the violation keeps the schema opinionated and the data intact, which is the same candidate/confirmed reasoning that made automatic extraction safe to run at all.

**Alternatives considered:**

- *Trigger-enforced rejection, matching `relationship_vocab`'s FK.* Rejected on both counts above. The vocab FK is safe precisely because vocabulary rows are deprecated rather than deleted; constraints have no equivalent soft path.
- *Reject at the application layer, before insert.* Same destructive-edit problem, and it throws away the evidence that would tell an operator their constraint is wrong rather than their data.

### D3. `concept.class_id` is nullable

**Choice:** `ALTER TABLE opencg.concept ADD COLUMN class_id UUID NULL REFERENCES opencg.ontology_class(class_id)`. Unclassified concepts are legal and sort first in the review queue.

**Rationale:** Every concept extracted before this change is genuinely of unknown kind. A `NOT NULL DEFAULT <Thing>` would be a lie stored in the database — indistinguishable from a concept an operator deliberately classified as the root. Null means "nobody has said", which is the truth, and it makes the backlog directly queryable.

**Alternatives considered:**

- *`NOT NULL` defaulting to `Thing`.* Rejected: destroys the distinction between unclassified and deliberately-generic.
- *Separate `concept_classification` table.* Rejected as over-normalised for a single-valued attribute under D1.

### D4. Absence of constraints means unconstrained

**Choice:** A relationship type with zero `ontology_constraint` rows accepts any domain and any range. Constraints narrow; they never widen.

**Rationale:** Preserves current behaviour exactly on day one — the seeded constraints cover the six code relations, and the four purely semantic relations (`mentions`, `related_to`, `supersedes`, `derived_from`) ship unconstrained because there is no defensible restriction on what may `mention` what. It also makes adoption incremental: an operator constrains one relation, watches the violations queue, and moves on.

**Alternatives considered:**

- *Closed-world default (no constraint means nothing is legal).* Rejected: every existing edge becomes a violation the moment this change lands, and the queue becomes noise.

### D5. Subsumption resolved by recursive CTE, not a materialised closure table

**Choice:** Ancestor and descendant sets are computed with `WITH RECURSIVE` against `ontology_class` at query time. Constraint checks and class-filtered traversal both expand through it.

**Rationale:** The class tree is operator-authored and will hold tens of rows, not millions; a recursive walk over it is trivially fast and cannot drift out of sync with its source. A closure table is a cache, and a cache that must be invalidated on every class edit is a correctness liability bought for performance nobody needs at this size.

**Alternatives considered:**

- *Materialised closure table.* Revisit if a deployment authors a genuinely large ontology, which is exactly the case an external-ontology import would create. Noted as a trigger for OQ2.
- *Postgres `ltree`.* Rejected: encodes the path in the key, so reparenting a class rewrites every descendant.

### D6. The extraction prompt is generated from the ontology

**Choice:** `graph/extract.py` stops embedding a literal relation list. It builds the prompt from the live ontology — the class names with one-line descriptions, and the legal `(domain, relation, range)` triples — and asks the model to return a class alongside each concept. The generated prompt is bounded: if the rendered ontology exceeds a configured character budget, classes are included in full and constraints are truncated with a note, because a class the model has never heard of is worse than a constraint it has to guess.

**Rationale:** A hand-maintained prompt drifts from a runtime-editable ontology the first time an operator adds a class. Generating it means the operator's edit takes effect on the next chunk with no code change.

**Alternatives considered:**

- *Keep the prompt literal, validate the output against the ontology afterwards.* Rejected: the model would keep proposing classes that do not exist, so every operator extension would show up as a violation spike rather than as better extraction.
- *Two model calls — classify, then relate.* Rejected: doubles ingest-time token spend for a task the model can do in one pass, and per-stage token accounting is a load-bearing project requirement.

### D7. The code path classifies deterministically; only the prose path guesses

**Choice:** `graph_writer` maps graphifyy's `symbol_kind` onto core classes (`class → Class`, `function → Function`, `method → Method`, `module → Module`) and writes `class_id` with the same `confirmed` state it already gives code-extracted rows. No model call.

**Rationale:** Consistent with the existing split — parsing is not an opinion, so a parsed classification does not belong in a review queue. This also seeds the graph with a correctly-classified backbone that the violations queue can immediately measure prose-extracted edges against.

### D8. The ontology lives in Postgres only, not mirrored into AGE

**Choice:** `ontology_class` and `ontology_constraint` are ordinary Postgres tables. Class information reaches traversal by hydration — traversal already reads node metadata back from `opencg.concept` after the Cypher match, and `class_id` rides along on that read.

**Rationale:** The AGE mirror exists for one reason: multi-hop edge traversal in openCypher. The ontology is not traversed multi-hop; it is looked up and expanded one tree at a time. Mirroring it would add a second consistency obligation for zero query capability.

**Alternatives considered:**

- *Model classes as AGE vertices with `IS_A` edges.* Rejected: subsumption in Cypher is not simpler than a recursive CTE here, and it would put the schema and the data in the same graph.

### D9. Editing a constraint schedules a re-check; it never rewrites edges

**Choice:** Adding, editing, or deleting a constraint marks affected edges `constraint_state = 'unchecked'` and enqueues a re-check that recomputes `ok` / `violation`. Edge `state` (`candidate` / `confirmed` / `tombstoned`) is never touched by a schema edit.

**Rationale:** Keeps the two axes independent and legible: `state` is what a *human* decided about an edge, `constraint_state` is what the *schema* says about it. An operator narrowing `depends_on` should surface newly-suspect edges for review, not silently demote edges a colleague already confirmed.

### D10. The ontology absorbs `relationship_vocab`

**Choice:** Relationship types become ontology objects rather than a neighbouring table the ontology points at. `opencg.relationship_vocab` is renamed `opencg.ontology_relationship`, keeps every existing column (`name`, `description`, `inverse`, `directed`, `deprecated_at`), and gains `origin TEXT NOT NULL` (`core` / `operator`) to match `ontology_class`. Governance moves with it: `/ontology/relationships` becomes the canonical admin surface, the audit `target_kind` becomes `ontology_relationship`, and one ontology version now covers classes, relationship types, and constraints together.

`name TEXT` stays the primary key. The rename therefore leaves `relationship_edge.type`'s foreign key intact — Postgres binds a constraint to the table, not to its name — so the shipped guarantee that `type = "nonsense"` fails *at the database* survives byte-for-byte. No edge row is touched.

**Rationale:** A schema layer that governs what kinds of things exist but not what kinds of arrows exist is half a schema. The three objects are already one concept in every operation that matters: a constraint is meaningless without both a class and a relationship type, the extraction prompt renders all three together, and an operator narrowing the model edits them in one sitting. Splitting them across two APIs with two audit vocabularies and two versioning stories would make every one of those operations reach into two places for no gain.

The timing argument is decisive. Absorbing is cheap now and expensive later: `/graph/vocab` has no external consumers today, so the move costs a rename and an alias. Once operators have written against it, the same move is a breaking API change. Deferring the decision was itself the risk.

Domain and range stay in `ontology_constraint` rather than becoming columns on the relationship row. A type carries *many* legal triples evaluated disjunctively (D4) — `imports` legitimately runs `Module → Module` and `Module → ExternalPackage` — so columns would permit exactly one and force the second into a duplicate type. Absorption is about who governs the object, not about flattening its cardinality.

**Alternatives considered:**

- *Reference `relationship_vocab` by FK and leave it under `/graph/vocab`.* The narrower reading this change was originally written to. Rejected: it leaves the ontology unable to answer "what does this deployment's model look like" without a second API, and it makes the eventual merge a breaking change instead of a rename.
- *Drop `relationship_vocab` and derive legal types from the constraint table.* Rejected: it destroys the FK that makes unknown edge types a database error, and a type with no constraints (D4's unconstrained case) would cease to exist entirely.
- *Keep the table name and move only the API.* Rejected as the worst of both — the storage layer would keep saying `vocab` while every other surface said `ontology`, which is exactly the drift this decision exists to remove.

**Consequence for the append-only audit log.** Historical rows carry `target_kind = "vocab"` and cannot be rewritten; the log forbids `UPDATE` by trigger and that rule is not being bent for a rename. Readers MUST accept both values, with `vocab` understood as the pre-absorption spelling.

## Risks / Trade-offs

- **The seeded ontology is a guess about a corpus we have partly seen.** The code half is safe — it mirrors graphifyy's own symbol kinds. The document/topic half is inference from one ingested cookbook repo. Mitigation: the core is small and carries no privilege at query time, so a deployment that disagrees can extend or ignore it without forking.
- **Generated prompts increase ingest-time token spend** roughly in proportion to ontology size, and an operator can grow the ontology without seeing the cost. Mitigation: D6's character budget, plus the existing `opencg_tokens_total` counter already broken down by stage, so the increase is visible rather than inferred.
- **Advisory constraints can be ignored indefinitely.** Nothing forces an operator to drain the violations queue, so the ontology can become decorative. Accepted: the alternative (D2's enforcement) is worse, and `opencg_constraint_violations_total` makes neglect measurable.
- **Classification quality on the prose path is unmeasured.** We have no labelled set, so "does `gemma3:4b` classify concepts well" is currently unanswerable. The violations queue is the first instrument that would tell us, which is part of why it ships in this change rather than a follow-up.
- **Two review queues now exist** (candidate concepts/edges, and constraint violations) and they overlap: an edge can be both a candidate and a violation. Mitigation: the UI presents violations as a filter over the existing queue rather than a separate inbox.

## Migration Plan

1. `infra/postgres/init/060_ontology.sql` creates both new tables and seeds the core class tree and constraints. `050_` is already taken by `050_graph_audit.sql`, and the script must run after both it and `040_graph.sql` because it renames a table those two create and reference.
2. The same script renames `opencg.relationship_vocab` to `opencg.ontology_relationship` and adds its `origin` column, backfilled to `core` for the ten seeded rows (D10). The rename carries the existing primary key and the `relationship_edge.type` foreign key with it, so no edge row is rewritten and unknown edge types keep failing at the database.
3. The same script adds `class_id` to `concept` and `constraint_state` to `relationship_edge`, both nullable/defaulted so the migration is non-blocking on existing rows.
4. Existing concepts stay `class_id IS NULL`; existing edges start at `constraint_state = 'unchecked'`. A one-shot re-check pass classifies them `ok` or `violation` against the seeded constraints. Because the seeded constraints only cover code relations and code-extracted concepts are classified by D7's deterministic map, the first pass is expected to leave prose edges `unchecked` rather than falsely flagging them.
5. `/graph/vocab` is kept as a deprecated alias of `/ontology/relationships` for one release so any local tooling keeps working, and is removed in the follow-up that archives this change.
6. `opencg-ingest re-extract` gains an ontology-version guard alongside its existing extractor-version guard, so re-running it after an ontology edit reclassifies rather than skips.
7. Rollback is dropping the two new tables and the two added columns and renaming `ontology_relationship` back; nothing in this change destroys existing data, which is the point of D2, D3, and D10.

## Open Questions

- **OQ1: Does the ontology absorb `relationship_vocab`, or sit alongside it?** **Resolved: it absorbs it.** See D10. The spec is written to that reading throughout — `ontology_constraint` references `ontology_relationship(name)`, and relationship types are governed by the ontology admin API rather than by `/graph/vocab`.
- **OQ2: Should the ontology be tenant-scoped?** `concept` carries `tenant` and dedupes on `(tenant, dedupe_key)`. The relationship vocabulary never carried a tenant at all. This change follows that precedent and makes the whole ontology — classes, relationship types, and constraints — deployment-global, which is consistent with single-tenant-per-deploy in v0. Under D10 this is now one decision covering three tables rather than a per-table judgement call, which is a small argument in its favour and a larger migration if multi-tenancy ever lands.
- **OQ3: What backfills the existing unclassified corpus?** Options are a bulk `re-extract` (accurate, costs tokens over the whole corpus), a cheap heuristic pass over `is_code_path` and chunk metadata (free, only classifies code, which D7 largely covers for new content anyway), or leaving it to operators through bulk actions in the review queue. Not decided; deliberately outside this change's scope so the layer can ship without a corpus-wide model run.
- **OQ4: Should a class carry expected edge types for UI affordances?** Showing an operator "concepts of kind `Service` usually have `depends_on` edges" is derivable from `ontology_constraint` and needs no schema. Noted only so it is not mistaken for a missing column.
