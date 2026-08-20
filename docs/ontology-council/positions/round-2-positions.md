# Round 2 — Independent seat positions

Three seats, identical briefs, different model families, formed without sight of each other or of the incumbent `add-ontology-layer` draft. Recorded verbatim in substance.

- **Seat A** — Claude Opus 5 thinking @ max
- **Seat B** — GPT-5.6 sol @ max
- **Seat C** — Grok 4.5 @ high

**All three verdicts: do not build an ontology layer / do not make ontology a pillar.**

---

# Seat A (Opus 5)

## Verdict

**No ontology layer.** What is proposed under that name is three separable things with three different verdicts, and bundling them into an 83-task change is the error. openCG should (a) **fix and close the node-kind field it already ships**, currently populated by a broken heuristic and rendered to users as fact; (b) **ship exactly one consumer that makes a node kind change software behaviour** — a kind filter on retrieval, which lives in the Qdrant payload and not in the graph at all; and (c) **defer every class-hierarchy-shaped decision** until a real corpus has been ingested and censused.

The decisive fact is not philosophical: **openCG's graph currently has no reader.** `/retrieve` never touches `GraphStore` (`app.py:117-249` binds `catalog`, `audit`, `vector`, `embeddings` and never `app.state.graph`), and the only two live MCP tools cannot be composed because nothing maps an `entity_id` to a `concept_id`. Every system in R1 where a schema is load-bearing — Palantir, TigerGraph, Airbnb, Graphiti, dbt/Minerva — built the query path first and hardened the schema to serve it. **Adding a type system to an unconsumed graph inverts that order.**

## What it is

Three named artefacts, in dependency order.

**(A) `symbol_kind` as a closed, correct, deterministic node-kind enum.** One value per concept, no hierarchy, no inheritance, no multiple classification. **Seven values:** `module`, `class`, `function`, `method` (the four the archived spec already mandates at `openspec/specs/knowledge-graph/spec.md:131`), plus `topic` for prose concepts, `external_module` for import targets minted at `graph_writer.py:172-208`, and `external_symbol` for names graphifyy references but never sees declared. Enforced by a `CHECK`, indexed, editable through `PATCH /graph/concepts/{id}`, derived **once** per node instead of twice.

**(B) A payload-level kind filter on `/retrieve`.** `symbol_kind` copied into the Qdrant payload and threaded through `hybrid_retrieval.run` from the already-declared `RetrievalRequest.filters`.

**(C) Report-only endpoint plausibility, gated on measurement.** An allow-table of `(edge_type, from_kind, to_kind)` triples **seeded from an observed census, not from imagination**, joined against edges in an idempotent batch job writing a findings table. It never blocks a write.

What the brief's framing understates: openCG **already has a real edge-type constraint.** `relationship_edge.type REFERENCES relationship_vocab(name)` is the only genuine schema enforcement in the graph, and `POST /graph/vocab` keeps AGE edge labels in sync in the same transaction. **That is not broken and must not be rewritten.**

## The consumer

**The consumer is `filters` on `POST /retrieve`, and it does not involve the knowledge graph.**

`symbol_kind` is already computed and stored in chunk metadata (`chunking.py:242`, `:272`, `:301`), reaching Postgres inside `opencg.entity.metadata`. It is **not** copied into the Qdrant payload — the payload dict at `pipeline_runner.py:163-175` carries nine keys plus `symbol_id` and stops. Meanwhile `VectorIndex.search` already accepts `filters` (`vector.py:59`) and `_build_filter` already turns arbitrary payload keys into Qdrant `must` conditions (`vector.py:147-156`). `RetrievalRequest.filters` is declared (`types.py:25`), exposed in the MCP tool schema (`tools.ts:40`), forwarded by the MCP client (`tools.ts:183`) — **and silently discarded**, because `hybrid_retrieval.run` has no `filters` parameter and omits the kwarg at its `vector.search` call.

**So: copy one payload key, add one parameter, pass it through.** An MCP client can then say "answer from functions and methods only, not from README prose," and `retrieve_for_context` — openCG's actual product surface — changes behaviour. Best evidential support available: R3 §3's Balog-line results, **+44% relative NDCG@10 with automatic type detection**. R3 is right that the transfer gap to chunk RAG is large and unproven; **I am not claiming the effect transfers. I am claiming this is the cheapest place to find out.**

**Three honest consequences.**

**First, this consumer does not need the `concept` table at all.** That is uncomfortable for the ontology framing: the best-evidenced use of node types in openCG is reachable without touching the graph, the extractor, or the vocabulary.

**Second, I must name the design hazard myself.** `entity.metadata` has **no GIN index**, so the lexical leg cannot honour the filter without one. Fusing a *filtered* dense ranking with an *unfiltered* lexical ranking through RRF produces a ranking that neither respects nor ignores the filter — **strictly worse than no filter**, and the kind of bug that hides for months. Fix: `CREATE INDEX entity_metadata_gin ON opencg.entity USING gin (metadata jsonb_path_ops)` plus a predicate in `lexical_search`. **Non-negotiable, not optional.**

**Third, the highest-value graph work available is not ontology work.** The entity→concept bridge R0 §9.10 calls missing is missing only as an *endpoint*; **the join key already exists in the data.** On the code path, `concept.symbol_id` and chunk `metadata->>'symbol_id'` are literally the same value — graphifyy's `node["id"]`, bound at `graph_writer.py:152` and `chunking.py:272`/`:301` — and `concept_symbol_ix` already indexes it. `GET /graph/concepts/for-entities?entity_ids=…` is two SELECTs over indexed columns. **It needs no node classes.**

## Mechanism

**Correcting the kind.** Two near-copy derivations disagree today: `graph_writer._kind_from_label` and `chunking._symbol_kind`. Both fall through to `return "class"` for any label not ending in `()`.

**I closed R0's open question by downloading the pinned wheel (`graphifyy-0.8.38`, per `uv.lock:264`) and reading `_extract_generic`:**

- **graphifyy emits no per-node kind.** `add_node` constructs exactly `{id, label, file_type, source_file, source_location}` (`graphify/extract.py:2222-2232`). The chunker's docstring hope — "until we wire in graphifyy's own kind hints" — is **currently unimplementable** without patching upstream.
- **But the distinction is deterministically known and discarded.** `LanguageConfig` holds `class_types`, `function_types`, `import_types` as separate frozensets (`:431-433`; Python `class_definition` vs `function_definition` at `:1836-1837`), and the AST walk branches on exactly those (`:2279`, `:2840`). And the file node is created as `add_node(file_nid, path.name, 1)` (`:2258-2259`) — **label is the bare filename. That is upstream confirmation of R0's fact #2**: `_kind_from_label("context_tools.py")` returns `"class"`, and `"module"` is unreachable.

Fix: derive kind **once** in `_extract_code` (`pipeline_runner.py:284-317`) — the only place chunks and the graphify result are simultaneously in scope — and pass a `node_id → kind` map into `write_code_graph` instead of re-deriving from the label. Reuse the module filter the chunker already gets right (`chunking.py:182-185`). Then `CHECK`, `CREATE INDEX concept_kind_ix`, and **add `symbol_kind` to `patch_concept`'s allow-list.** That last matters more than it looks: today a reviewer **cannot** correct a wrong kind through any API, and `ON CONFLICT … COALESCE` makes the first value permanent. **A field that is displayed, wrong, and uncorrectable is worse than no field.**

**Endpoint plausibility, and R2's join claim.** R2 §13.4 is right and it is the most useful sentence in the dossiers: *the primitive under discussion is a join.* Adopted wholesale, including its terminology discipline — **not** `domain`/`range`.

```sql
SELECT e.edge_id, e.type, f.symbol_kind, t.symbol_kind
FROM opencg.relationship_edge e
JOIN opencg.concept f ON f.concept_id = e.from_concept_id
JOIN opencg.concept t ON t.concept_id = e.to_concept_id
LEFT JOIN opencg.edge_endpoint_rule r
  ON (r.edge_type, r.from_kind, r.to_kind) = (e.type, f.symbol_kind, t.symbol_kind)
WHERE r.edge_type IS NULL
  AND f.symbol_kind IS NOT NULL AND t.symbol_kind IS NOT NULL;
```

That is the entire mechanism. NULL kinds excluded deliberately: **absence is not a violation**, because with a ~75% recall ceiling an extracted graph's absences carry no information. Results land in `opencg.graph_finding` with SHACL's result fields as columns — including **`checked_coverage`**, because R2 trap #6 is real and `0 violations` must never be confusable with `nothing was checked`. Runs as an idempotent, non-mutating `POST /graph/validate`, **not a trigger**. On violation **nothing happens to the edge**; a findings row appears and the candidate tab gains a "flagged" filter and a **bulk-demote action** — bulk triage is the behaviour change, answering R0 §9.5 where every review action is single-target.

Apache AGE untouched: one label per vertex, no constraint DDL, used solely as a bounded candidate-ID generator. **A per-class vertex label buys nothing and costs a migration.**

## Refusals

- **Any class hierarchy, subsumption, or inheritance — single or multiple.** R2 §8.2's own table concludes a few hundred classes needs no encoding at all. R2 trap #9 is a trap you avoid by not entering. **Flat closed enum. No parent column.**
- **The words `domain` and `range`.** R2 trap #2, plus R2 §0's inverted semantics. **Call it `edge_endpoint_rule`.**
- **Write-time rejection, anywhere.** R3 §7: 32–37% of uncorrected LLM triples violate a real ontology. Blocking either makes ingestion fail constantly or drives an exception list until enforcement means nothing.
- **Sending the class set to `gemma3:4b` as a hard structured-output schema.** R3 §4's constraint tax. And note what the code proves: `_RESPONSE_SCHEMA` has **never** been transmitted, and nobody noticed — evidence the extractor's output shape is not the binding constraint.
- **Absorbing or rewriting `relationship_vocab`.** Its FK is the one thing in this schema that works. Its actual defects are small and separately fixable: `inverse` and `directed` are **dead columns read by nothing**, and `_assert_active_vocab` is called from exactly one site (`patch_edge`), so deprecating `calls` would not stop `_RELATION_MAP` — a compile-time constant — from writing a single one. **Two ~10-line fixes, not a new artefact.**
- **A user-editable class vocabulary in v1.**

**One thing I would build instead, which the ontology framing obscures.** `load_vocabulary` selects every non-deprecated row with **no source filter**, so `calls`, `imports`, `uses` — seeded explicitly for graphifyy's tree-sitter output — are offered to `gemma3:4b` reading Markdown. Add `source TEXT` (`'prose'|'code'|'both'`) to `relationship_vocab` and filter the prompt on it: **three impossible choices vanish from the model's menu for about five lines.** Under R3 §1's ablations that is the highest-leverage extraction change on the table. **It is not an ontology.**

## Falsifiers

**E1 — the corpus census. Half a day, before any spec is written.** There is no configured corpus and the only fixture is two files. R0 §7.5 says the code/prose ratio "cannot be answered from the repository." **That is not a research gap — it is a 20-minute experiment nobody has run.** Ingest one real repository, then four queries:

1. `SELECT symbol_kind, count(*) FROM opencg.concept GROUP BY 1 ORDER BY 2 DESC`
2. The same split by `extractor_version` — the coverage hole between `graphifyy/%` and `text-extractor/%`
3. `SELECT type, count(*) FROM opencg.relationship_edge GROUP BY 1` — which of the ten relations are actually used
4. **The endpoint cross-tab** — the join above run as a *descriptive* query with no rule table: `GROUP BY e.type, f.symbol_kind, t.symbol_kind`

**Query 4 is the falsifier for (C).** If the top five triples cover >90% of edges, an allow-table is cheap to seed and violations will be informative. **If it is a long flat tail, the findings table becomes a permanently red dashboard — operationally identical to having no validation — and I withdraw (C) on the spot.**

**E2 — the retrieval A/B**, gated on E1 producing a corpus. ~30 queries naming a code symbol, run bare vs with `filters={"symbol_kind": ["function","method"]}`, measuring whether the intended chunk is in the top 5. **If the filter does not move recall@5, my strongest consumer is dead, (B) should not ship, and the honest verdict collapses to R4 §10's steelman.**

## Cruxes

1. **What fraction of concepts in a real corpus carry a non-NULL, non-wrong kind?** Prose concepts and external import targets are NULL forever; every file node is wrong. **Below ~40% coverage, both (B) and (C) are built on a field describing a minority of the graph — fix the bug, close the enum, ship nothing else.** Above ~70%, the consumer story holds.
2. **Does the `(type, from_kind, to_kind)` distribution concentrate?** Concentrated ⇒ build (C). Flat ⇒ **withdraw (C) entirely.**
3. **Does a kind filter change retrieval recall?** Load-bearing for the whole position. **If E2 shows no movement, no node-typing work is justified beyond the correctness of a field openCG already displays.**

**One process claim I will defend.** The proposal that reaches the OpenSpec approval gate should contain a **census table, not an inference.** Every argument in this council, including mine, is currently reasoning about a graph nobody has observed.

---

# Seat B (GPT-5.6 sol)

## Verdict

openCG should **not add an ontology layer or make ontology a pillar now**. It should first make its existing typed-edge graph **accurate and consumable**: repair the code-symbol kind contract, scope predicates to their extractors, support deterministic kind filters, respect direction, and establish entity-to-concept provenance. Persistent domain classes, endpoint rules, and hierarchy remain a falsifiable follow-up.

**This is not a vote against typing.** R1 shows typed schemas are valuable when they control extraction, queries, ranking, validation, or actions. openCG currently has **none of those consumers** for a general node-class system. **Building a class vocabulary first would be semantic supply before demand.**

## What it is

openCG already has a **typed-edge, evidence-bearing property graph**, not an ontology. It lacks general node classes, class inheritance, endpoint constraints, logical inference, and schema-versioned class assignments. **That is acceptable for the behaviour openCG actually ships.**

The next feature should be called a **graph contract**, not an ontology:

1. Make `symbol_kind` a truthful, nullable code facet with exactly `module`, `class`, `function`, `method`. **Prose concepts and unresolved external symbols remain unknown rather than being forced into invented classes.**
2. Compute code kind **once** from authoritative parser information and reuse it for chunks, concepts, and vector payloads. A merged chunk contains several symbol kinds; **`"merged"` is not itself a symbol kind.**
3. **Scope predicates by producer.** The prose extractor may use the seven semantic predicates; the deterministic code writer may use `calls`, `imports`, `uses`, `defined_in`. `defined_in` legitimately belongs to both.
4. Make the existing facet usable in graph and retrieval queries.
5. **Record every concept occurrence against its source entity** so retrieval results can later be mapped to graph concepts.

## The consumer

**There is no current consumer for a general ontology. That is the decisive finding.**

The smaller graph contract has immediate consumers:

- **`GET /graph/traverse` gains `direction=in|out|both` and `symbol_kinds=…`.** "Show outgoing calls to functions and methods" then returns a server-filtered result instead of a truncated undirected neighbourhood. Today the AGE pattern **and** the Python BFS are both undirected.
- **`POST /retrieve` honors `filters.symbol_kind`.** The request already contains `filters`, Qdrant already supports payload filters, but retrieve and `hybrid_retrieval.run` discard them and ingestion omits `symbol_kind` from payloads.
- **The prose extractor stops seeing `calls`, `imports`, `uses`.** This changes model output and prevents structurally irrelevant predicates from reaching storage.
- Invalid code-kind values fail deterministically, while tests catch semantic misclassification such as a file node becoming `"class"`.

## Mechanism

1. Nullable `CHECK` on `symbol_kind` for the four code kinds; index on `(tenant, symbol_kind)` where non-null; backfill after correcting the classifier.
2. Add **`relationship_vocab_producer(relationship_name, producer)`** with FK to `relationship_vocab`, `producer IN ('code','prose')`, composite PK. Both writers must also reject deprecated predicates.
3. Replace the duplicate label heuristics with **one classifier**. Prefer a first-class graphifyy kind if available; otherwise identify the module node explicitly from path/node metadata before applying the function/method/class heuristic.
4. Add **`concept_occurrence(concept_id, entity_id, producer, extractor_version, created_at)`**. Both writers insert occurrences for every source, rather than relying on `concept.source_entity_id`, **which records only one source.**
5. Copy `symbol_kind` into Qdrant payloads. **Pass filters to the dense leg AND apply the same predicate to the Postgres lexical leg; filtering only Qdrant would produce inconsistent RRF input.**
6. **Apply `symbol_kinds` and direction during graph edge selection and reachability, before the result limit.** Merely filtering hydrated nodes afterward would produce incomplete paths.
7. Load the prose prompt vocabulary through `relationship_vocab_producer`. The declared JSON schema is currently collapsed to `format: "json"`; **production should not silently claim stronger enforcement.** Prompt-only JSON versus actual schema-constrained output must be ablated because R3 documents the small-model "valid-looking but wrong" constraint tax.

**R2 is correct that endpoint validation is fundamentally a join. It is also a reason not to construct an ontology subsystem prematurely.** The experiment can use a temporary relation of allowed `(relationship_type, source_kind, target_kind)` tuples. **Unknown endpoint kinds count as uncovered, not violations.**

If the experiment succeeds, the persistent mechanism should be one versioned table named **`edge_endpoint_rule`** with `relationship_type`, `source_type`, `target_type`, `severity`, `schema_version`. **Do not call the fields `domain` and `range`.** Validation non-mutating; retain a candidate edge while recording a structured finding. **A reviewer may promote only after resolving or explicitly overriding a violation, with the override captured in the append-only graph audit.** Missing relationships **must never** be violations for prose extraction.

## Refusals

- No OWL, RDFS runtime, RDF store, or reasoner. **OWL domain/range would infer that a bad endpoint has the expected type rather than flagging the bad edge.**
- No `domain`/`range` terminology. Use `source_type` and `target_type`.
- No class hierarchy, subsumption closure, `ltree`, multiple inheritance, or inferred classification.
- **No default business taxonomy** such as Person, Organization, Service, Topic, Document, Dataset. With `ingestion.git.repos: []` those classes would **encode council guesses rather than deployment evidence.**
- **No forced `Other` class.** Unknown must remain a first-class coverage result.
- No automatic prose typing or promotion based on `gemma3:4b` confidence.
- No hard write rejection for LLM-derived endpoint mismatches initially. **Deterministic code-contract violations may fail hard.**
- No graph expansion or ontology-based rank boost in `/retrieve` before evaluation.
- **No ontology editor, ontology tab, or ontology-specific pillar.** An authoring surface would turn an unproven vocabulary into a second product requiring ownership, migrations, compatibility policy, and support.
- No open-ended per-deployment ontology language.

## Falsifier

A three-day **shadow-schema spike** without a production migration:

1. Ingest openCG itself and one repository representative of an intended deployment. **If no representative corpus can be named, the project does not yet possess evidence capable of justifying an ontology.**
2. Sample ~200 edges, stratified by extractor and predicate. **Two reviewers** label factual correctness and endpoint types using ≤8 flat, corpus-derived types plus `unknown`.
3. Put type assignments and allowed tuples in temporary Postgres tables. Run the R2 join; measure coverage, precision of violation findings, false rejection of valid edges.
4. 30–50 corpus-grounded queries including a measured type-seeking slice. Compare hybrid baseline vs explicit type filtering; **report nDCG@10 or precision@10, not schema-validity counts.**
5. Same prose chunks through baseline vs type-guided extraction, measuring **fact precision and recall — not merely JSON validity.**

**Falsified if:** a small flat schema achieves ≥90% useful coverage with inter-reviewer **κ ≥ 0.8**, endpoint findings identify **≥30% of false edges at ≥95% precision** while rejecting **<5% of true edges**, and type-aware querying improves **nDCG@10 by ≥0.05** on a slice representing **≥10% of expected MCP traffic**. At that point build the minimal schema, because a consumer has paid for it.

## Cruxes

1. **Do real users repeatedly ask questions with stable type intent?**
2. **Does the corpus admit a small, reproducible type system?** If classes are corpus-specific, ambiguous, or mostly `unknown`, the vocabulary is not ready.
3. **Is there a durable owner and bounded operational load?** **If ownership is "the community" or the queue is expected to drain itself, I do not accept the maintenance obligation.**

---

# Seat C (Grok 4.5)

## Verdict

openCG should **not** add an ontology layer as a system pillar. It needs to **finish the type work it already half-built for code**, wire that type into queries and UI that actually use it, and **refuse to invent a second product** until there is a measured consumer that cannot be served by relation types, hybrid retrieval, and fixed code kinds. **Building a general ontology under these conditions is ceremonial schema.** Build a **code-kind discipline** instead.

## What it is

Call it a **code-kind discipline**, not an ontology.

| Element | Definition |
|---|---|
| Kind set | Closed: `module \| class \| function \| method`. Nullable only for non-code concepts. |
| Source of truth | Prefer graphifyy's own kind hints if present; else one shared heuristic used by both chunker and graph writer. Fix the bug mapping every non-`()` label to `"class"`. |
| Storage | Keep `symbol_kind TEXT`. Add `CHECK` and a filter-usable index. **Do not invent a separate `concept_class` table or AGE multi-label scheme** (AGE allows one vertex label). |
| Write policy | Code path sets kind. External import targets: `module` when the edge is `imports`, else null. Prose: null. |
| **Consumers (mandatory — without these, stop)** | (a) `GET /graph/traverse?kinds=`; (b) `GET /graph/concepts?kinds=`; (c) graph map colours/filters by kind; (d) concepts table kind column. |
| Soft endpoint patterns (optional second slice, code relations only) | Allowed `(relation, from_kind, to_kind)` triples for `calls`, `imports`, `uses`, `defined_in`. Checked as a **join** at write and as a batch report. Violations → warning finding + counter; **do not reject.** Name these **endpoint patterns**, never "domain/range". |

**No class hierarchy. No subsumption encoding. No prose types. No reasoner. No triple store.**

**Why this is not "an ontology layer":** R1's durable jobs for ontology are canonicalization, extraction control, query control, inference, validation, governed action. This proposal does **query control for code kinds** and optionally **soft validation for deterministic edges**. **Naming it "ontology" would import the wrong expectations and the RDFS domain/range trap.**

## The consumer

| # | Consumer | Behaviour change |
|---|---|---|
| C1 | `GET /graph/traverse` | `kinds=function,method` — answers R0 §9.1 "show me only the functions in this neighbourhood" |
| C2 | `GET /graph/concepts` | `kinds=` — enables aggregation and review without scanning 200 untyped rows |
| C3 | Admin graph map / concepts tab | Colour or filter by kind; today kind is a detail-panel suffix only and the map model drops it |
| C4 (optional) | Soft endpoint report | Bulk triage signal for structurally implausible code edges, without write rejection |

**Not a consumer, and I refuse to treat them as one:** "enables future GraphRAG" (retrieve does not read `GraphStore`); "improves extraction quality" (no gold corpus to measure); "governance/glossary" (single-tenant self-host, no cross-org interoperability demand).

**If C1–C3 are not scheduled in the same change as kind constraints, do not ship the constraints.**

## Mechanism

1. **Unify heuristics** in one module shared by `chunking._symbol_kind` and `graph_writer._kind_from_label`. Module/file nodes → `"module"`.
2. Migration: `CHECK` on allowed values; index `(tenant, symbol_kind) WHERE symbol_kind IS NOT NULL`; backfill by re-deriving where possible, leave nulls.
3. Writes: code path sets kind; prose omits; **patch API may allow kind correction with audit** (today the allow-list is `{name, description, aliases}`).
4. Reads: add `kinds` to traverse and `list_concepts` SQL. AGE candidate Cypher stays as-is; authoritative filter remains in Postgres hydration + Python BFS.

**Soft endpoint patterns:**

```text
opencg.endpoint_pattern (
  relation  TEXT REFERENCES relationship_vocab(name),
  from_kind TEXT NOT NULL,
  to_kind   TEXT NOT NULL,
  PRIMARY KEY (relation, from_kind, to_kind)
)
```

**Check:** on edge write, join both endpoint kinds. **If either is null → skip the check (open/unknown, not violation — PG-Schema LOOSE spirit).** If both set and pair missing → findings row with SHACL-shaped fields, severity `warning`. **Do not fail the ingest.** Batch report must include **coverage: edges checked vs skipped for null kinds** (R2 trap 6: conforms ≠ checked).

**What deliberately does not run:** no RDFS/OWL entailment; no reasoner or triple store; no change to `/retrieve` in this work; no hard constrained decoding until gemma3:4b is measured. Fixing the `format: json` collapse is worthwhile plumbing; **it is not an ontology.**

## Refusals

1. An ontology pillar equal to ingestion or retrieval — recreates Semantic Web supply-before-demand.
2. OWL/RDFS, SHACL engines, triple stores, DL reasoners. **Borrow report shapes; do not adopt the stack.**
3. Naming validation fields `domain`/`range`.
4. **Class hierarchy / subsumption / `ltree` / closure tables for concept classes.**
5. Prose concept typing via gemma3:4b as authoritative classes.
6. Hard write rejection of edges on pattern violation.
7. GraphRAG / type-aware `/retrieve` inside this change. **Wire `entity_id↔concept_id` and measure multi-hop lift before ontology talk resumes for retrieval.**
8. Expanding the candidate review surface with new class adjudication.
9. Per-deployment custom class editors. **Do not ship Ontology Manager lite.**
10. Treating verbalized confidence 0.6 as ontology-quality control.

## Falsifiers

**A (kills "kinds need consumers / discipline first"):** ingest a real code-heavy repo; count `symbol_kind` distribution before the fix; confirm module nodes are mostly `"class"`. After a one-day fix + `kinds=` filter, have a human answer 20 "functions within depth 2 of X" questions via API vs manual scan. **If kind-filtered traverse does not reduce time-to-answer or error rate, fall back to display-only kind — no CHECK, no endpoint patterns.**

**B (kills my refusal of a broader ontology):** ≥200 labelled queries, hybrid alone vs hybrid + type-aware graph expansion after building `entity_id→concept_id`. **≥5 absolute points on the multi-hop slice ⇒ I was wrong to defer retrieval-facing types.**

**C (kills deferral of prose types):** human-gold 100 prose chunks; gemma3:4b with vs without a class whitelist; measure **triple precision/recall, not schema validity.**

## Cruxes

1. **Is there a present, valuable task requiring persistent node types beyond fixed code kinds?** My bet: **no.** Flip: operators or MCP clients regularly fail tasks needing class filters, evidenced by **real queries — not roadmap slides.**
2. **Will `/retrieve` consult the graph in the next meaningful increment?** My bet: **not until hybrid is maxed and multi-hop share is measured.** Until then ontology-for-RAG is **enablement theatre.**
3. **Is the graph's near-term value code-structure navigation or prose knowledge extraction?** My bet: **code-structure.** Flip: docs-heavy deployments dominate ⇒ extraction-control schemas matter more — **still as extraction post-filters, not an ontology pillar.**

---

# Lead's verification of disputed claims

Per "verify, do not vote," I checked Seat A's new evidence rather than accepting it.

**Seat A's graphifyy claims — all three confirmed** against the unpacked `graphifyy-0.8.38` wheel:

- `add_node` at `graphify/extract.py:2222-2231` constructs exactly `{id, label, file_type, source_file, source_location}`. **No kind field.** Seat C's design says "prefer graphifyy's own kind hints if present" — **they are not present.** That branch of C's spec is unimplementable as written.
- The file node is created as `add_node(file_nid, path.name, 1)` at `:2259` — **label is the bare filename**, which is the upstream root cause of every file node being recorded as `"class"`.
- `class_types` and `function_types` are separate frozensets in `LanguageConfig` (`:432-433`, per-language at `:1836-1837`). **The AST walk knows the distinction and discards it.**

**Seat A's entity→concept bridge claim — confirmed.** `graph_writer.py:152` binds `node["id"]` as the concept's `symbol_id`; `chunking.py:271` and `:300` bind that same `node["id"]` into chunk metadata. Same value on the code path, and `concept_symbol_ix` already indexes it. **Seat B's proposed `concept_occurrence` table is therefore not required for the code path**, though B's point stands that `concept.source_entity_id` records only one source and prose-path provenance is genuinely thin.
