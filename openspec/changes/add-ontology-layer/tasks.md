## 1. Pre-flight

- [ ] 1.1 Confirm **OQ2** (tenant scoping) stays deferred, or add a `tenant` column to all three ontology tables now if not. **OQ1 is settled — see D10: the ontology absorbs the relationship vocabulary.**

## 2. Storage and seed

- [ ] 2.1 Add `infra/postgres/init/060_ontology.sql` creating `opencg.ontology_class` and `opencg.ontology_constraint` with the columns, unique constraints, and FKs named in the spec. Use `060_`, not `050_` — `050_graph_audit.sql` already exists — and keep it below `090_grants.sql`.
- [ ] 2.2 In the same script, `ALTER TABLE opencg.relationship_vocab RENAME TO ontology_relationship`, add `origin TEXT NOT NULL DEFAULT 'operator'`, and backfill the ten seeded rows to `core`.
- [ ] 2.3 Assert the rename preserved the primary key and `relationship_edge.type`'s FK — do not drop and recreate either — and that no edge row was modified.
- [ ] 2.4 Seed the ten core classes: `Thing`; `CodeSymbol`, `Document`, `Service`, `Topic`; `Module`, `Class`, `Function`, `ExternalPackage`; `Method`.
- [ ] 2.5 Seed the seven core constraints for `calls`, `imports` (×2), `defined_in` (×2), `uses`, and `depends_on`.
- [ ] 2.6 `ALTER TABLE opencg.concept ADD COLUMN class_id UUID NULL REFERENCES opencg.ontology_class(class_id)`.
- [ ] 2.7 `ALTER TABLE opencg.relationship_edge ADD COLUMN constraint_state TEXT NOT NULL DEFAULT 'unchecked'` with a CHECK on `('unchecked','ok','violation')`.
- [ ] 2.8 Extend the `graph_audit_log` `target_kind` set to include `ontology_class`, `ontology_constraint`, and `ontology_relationship`; leave historical `vocab` rows untouched; verify the append-only trigger still applies.
- [ ] 2.9 Verify init ordering against a clean volume — `060_` must run after `040_graph.sql` and `050_graph_audit.sql` and before `090_grants.sql`, and Apache AGE's bundled script must still run first.
- [ ] 2.10 Grant on the renamed and new tables in `090_grants.sql`, so the rename does not silently drop a privilege.

## 3. Shared types

- [ ] 3.1 Add `OntologyClass`, `OntologyRelationship`, `OntologyConstraint`, `ClassRef`, and `ConstraintState` to `packages/shared`.
- [ ] 3.2 Mirror them in `packages/shared-py`.
- [ ] 3.3 Add `class_id` / class name to the existing `Concept` and `ConceptListItem` types, and `constraint_state` to `RelationshipEdge`, in both packages.
- [ ] 3.4 Retire or re-export any `RelationshipVocab` type in favour of `OntologyRelationship`, keeping the wire shape unchanged.

## 4. Ontology module in the pipeline

- [ ] 4.1 Create `services/pipeline/src/opencg_pipeline/ontology/` with a storage module following the `_Pool` / `_Conn` testing pattern used by `storage/graph.py`.
- [ ] 4.2 Implement class CRUD: create, read, list-as-tree, update, deprecate.
- [ ] 4.3 Implement ancestor-walk cycle detection, rejecting self-parent and indirect cycles before commit.
- [ ] 4.4 Implement subsumption with `WITH RECURSIVE` — ancestors-of and descendants-of a class.
- [ ] 4.5 Implement constraint list, create (rejecting duplicates with 409), and delete.
- [ ] 4.6 Move relationship-type CRUD out of the graph module: list, create, update, and deprecate under `/ontology/relationships`, preserving the existing `vocab_deprecated` rejection semantics.
- [ ] 4.7 Keep `/graph/vocab` working as a deprecated alias for one release, and mark it deprecated in the response and the docs.
- [ ] 4.8 Add `ontology/routes.py` mirroring `graph/routes.py`; register it on the FastAPI app.
- [ ] 4.9 Write an audit row for every ontology write, with before/after snapshots.

## 5. Constraint evaluation

- [ ] 5.1 Implement `evaluate_edge` returning `unchecked` / `ok` / `violation`, with disjunctive matching across a type's constraint rows and subtype expansion on both ends.
- [ ] 5.2 Return `unchecked` — never `violation` — when either endpoint has `class_id IS NULL`.
- [ ] 5.3 Return `ok` when the relationship type has zero constraint rows.
- [ ] 5.4 Call `evaluate_edge` on every edge write, in both the prose and code paths, and never let it raise into the caller.
- [ ] 5.5 Implement the re-check pass for a named relationship type; mark affected edges `unchecked`, then re-evaluate. Assert idempotence.
- [ ] 5.6 Trigger the re-check on constraint create, edit, and delete.
- [ ] 5.7 Add the one-shot migration re-check that classifies pre-existing edges.

## 6. Ontology-aware extraction

- [ ] 6.1 Replace the literal relation list in `graph/extract.py` with a prompt generated from the live ontology.
- [ ] 6.2 Render classes with descriptions, and legal relationships as `(domain, relation, range)` triples; render unconstrained types as accepting any endpoints.
- [ ] 6.3 Enforce the prompt character budget — classes in full, constraints truncated, truncation stated in the prompt.
- [ ] 6.4 Extend the requested JSON schema so each concept carries a proposed class; keep the existing defensive parsing.
- [ ] 6.5 Resolve proposed classes against the ontology; discard unknown or deprecated ones, leaving `class_id` null without failing the chunk.
- [ ] 6.6 Compute an `ontology_version` and attach it to the extraction span.
- [ ] 6.7 Add the ontology-version guard to `opencg-ingest re-extract` alongside the existing extractor-version guard.

## 7. Deterministic classification in ingestion

- [ ] 7.1 Map graphifyy's `symbol_kind` onto core classes in `graph_writer` (`module`, `class`, `function`, `method`).
- [ ] 7.2 Classify on-the-fly external import targets as `ExternalPackage`.
- [ ] 7.3 Leave `class_id` null and log at debug for an unmapped kind; never fail the write.
- [ ] 7.4 Confirm classification happens inside the existing single-transaction write.

## 8. Traversal

- [ ] 8.1 Add the `classes` parameter to `GET /graph/traverse`, expanding each named class to its descendants.
- [ ] 8.2 Exclude `class_id IS NULL` concepts when a `classes` filter is supplied; include them when it is not.
- [ ] 8.3 Add `include_violations`, defaulting to `false`.
- [ ] 8.4 Hydrate `class_id` and class name onto returned nodes, and `constraint_state` onto returned edges.
- [ ] 8.5 Reject an unknown class name with `400` naming the class.

## 9. Admin UI

- [ ] 9.1 Add the `/ontology` route.
- [ ] 9.2 Build `ClassTree` with create, edit, reparent, and deprecate; surface the server's cycle error inline.
- [ ] 9.3 Build `ConstraintMatrix` with add and delete, showing unconstrained types explicitly, and include create / edit / deprecate for relationship types themselves.
- [ ] 9.4 Build the violations queue with promote / edit / reject plus "reclassify endpoint".
- [ ] 9.5 Warn on constraint deletion with the count of edges to be re-evaluated.
- [ ] 9.6 Build `ClassBadge`; add it to the concept browser, concept detail, and candidate queue, with a distinct unclassified state.
- [ ] 9.7 Add the unclassified filter to the concept browser.
- [ ] 9.8 Add Next route handlers under `src/app/api/proxy/ontology/...`.
- [ ] 9.9 Write `*.stories.tsx` for `ClassTree`, `ClassBadge`, `ConstraintMatrix`, and `ViolationRow`, covering deprecated, unclassified, and unconstrained states.
- [ ] 9.10 Add `/ontology` to the admin nav.

## 10. Observability

- [ ] 10.1 Add `opencg_constraint_violations_total{relation,domain_class,range_class}`.
- [ ] 10.2 Add the `ontology_version` span attribute on `pipeline.graph_extract`.
- [ ] 10.3 Verify per-stage token accounting still emits both the span attribute and the `opencg_tokens_total` increment after the prompt change.

## 11. Tests

- [ ] 11.1 pytest: cycle rejection (direct and indirect), legal reparent.
- [ ] 11.2 pytest: subsumption across multiple hops; unrelated class does not match.
- [ ] 11.3 pytest: constraint evaluation — disjunction, unconstrained type, null endpoint stays `unchecked`, violation counted.
- [ ] 11.4 pytest: re-check idempotence, and that `state` is never touched by a schema edit.
- [ ] 11.5 pytest: prompt generation includes an operator-added class; budget truncation keeps all classes.
- [ ] 11.6 pytest: unknown proposed class is discarded without failing the chunk.
- [ ] 11.7 pytest: `symbol_kind` classification map, including the unmapped case.
- [ ] 11.8 pytest: traverse `classes` filter with subtype expansion, unclassified exclusion, unknown class rejected.
- [ ] 11.9 pytest: after the rename, an edge insert with an unknown `type` still fails at the database, and the ten seeded rows carry `origin = "core"`.
- [ ] 11.10 pytest: `/graph/vocab` and `/ontology/relationships` return the same vocabulary, and deprecating a type through the ontology API still rejects new edges with `vocab_deprecated`.
- [ ] 11.11 vitest: ontology page components, including the three edge-case states.
- [ ] 11.12 Extend `tests/smoke/run.sh` to assert the core ontology is seeded and that a class-filtered traverse returns only matching kinds.

## 12. Docs and explainer

- [ ] 12.1 Update `tools/explainer/content/07-ontology.md` — move `status:` off `planned`, replace the planned-flow narrative with the implemented one, cite real `file:` paths, and rewrite `## Gaps` to the honest post-ship list.
- [ ] 12.2 Update `tools/explainer/content/06-knowledge-graph.md` where classification and constraints change the described behaviour.
- [ ] 12.3 Make the ontology → knowledge-graph diagram edge solid in `tools/explainer/diagram.py` and update the diagram note.
- [ ] 12.4 Update `docs/OPERATIONS.md` with the ontology admin surface and the re-check operation.
- [ ] 12.5 Update the in-flight list in `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/opencg.mdc`.
- [ ] 12.6 Run `make explainer` and `make test-explainer`.

## 13. Ship

- [ ] 13.1 Run the full test suite.
- [ ] 13.2 Run `bash tests/smoke/run.sh` against the live stack.
- [ ] 13.3 Scan the staged diff for secrets.
- [ ] 13.4 Commit and push.
- [ ] 13.5 `openspec archive add-ontology-layer`.
