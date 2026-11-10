# knowledge-graph Specification

## Purpose

Maintain a named-relationship knowledge graph over the catalogue: deterministic code graphs from graphifyy, best-effort concept and relationship extraction from text, an editable relationship vocabulary, operator review of candidate relationships, evidence linking back to source chunks, and graph traversal.

## Requirements
### Requirement: Named relationship vocabulary

The graph schema SHALL represent concept-to-concept relationships as **named edges** drawn from a curated, extensible vocabulary stored in `opencg.relationship_vocab`. Vocabulary rows SHALL include `name` (primary key), `description`, `inverse` (optional name of the inverse relation), `directed` (boolean, default true), and `deprecated_at` (nullable timestamp). The vocabulary MUST be seeded at DB init with at least: `depends_on`, `defined_in`, `supersedes`, `mentions`, `related_to`, `causes`, `derived_from`.

The deterministic code extractor also requires the seeded names `calls`, `imports`, and `uses`, for a total of ten default vocabulary entries.

Edges in `opencg.relationship_edge` SHALL carry a `type TEXT` column with a FK to `relationship_vocab.name`. Inserts with an unknown name MUST fail at the database level.

The vocabulary table MUST be editable through an admin API: add a row, edit `description` / `inverse` / `directed`, mark a row deprecated. Marking a row deprecated MUST NOT delete it nor cascade to existing edges.

#### Scenario: Vocabulary FK rejects unknown names

- **WHEN** any caller attempts to insert into `opencg.relationship_edge` with `type = "nonsense"`
- **THEN** the insert fails with a foreign key violation

#### Scenario: Vocabulary seeded at init

- **WHEN** the database first starts under this change
- **THEN** `relationship_vocab` contains the ten seeded semantic and code relationship names with `deprecated_at IS NULL`

#### Scenario: Admin adds a new relationship type

- **WHEN** an admin posts `{name:"compatible_with", description:"…", inverse:"compatible_with", directed:false}` to the vocabulary admin endpoint
- **THEN** subsequent inserts using `compatible_with` are accepted

#### Scenario: Deprecation preserves existing edges

- **WHEN** an admin deprecates the `causes` vocabulary row
- **THEN** existing edges with `type = "causes"` continue to traverse normally
- **AND** new edge inserts with `type = "causes"` are rejected with a `vocab_deprecated` error

### Requirement: Deterministic code-graph extraction during ingestion

For every code file (where `is_code_path(path)` is true), the ingestion service SHALL invoke `graphify.extract([path])` exactly once per file, then persist the resulting `{nodes, edges}` to `opencg.concept`, `opencg.relationship_edge`, and `opencg.relationship_evidence` via the `graph_writer` module. The persistence MUST run inside a single Postgres transaction so a partial failure leaves no orphan rows.

Code extraction MUST NOT call any chat model. Code extraction MUST be best-effort: a graphifyy failure on one file MUST NOT abort the surrounding ingest — the file's catalog row and (text-fallback) chunks still upsert.

#### Scenario: Python file extraction is deterministic and silent

- **WHEN** ingestion processes a Python file containing two classes and a top-level function
- **THEN** `graphify.extract` is called exactly once for that file
- **AND** no chat-model call is made for any chunk derived from that file
- **AND** the resulting concepts and edges land in `opencg.concept` / `opencg.relationship_edge` in a single transaction

#### Scenario: Code file with zero symbols does not produce graph rows

- **WHEN** ingestion processes a `.py` file that contains only configuration constants (no `def`, no `class`)
- **THEN** the paragraph chunker handles embedding
- **AND** no concept or edge rows are written for that file

#### Scenario: Extraction failure does not abort the ingest

- **WHEN** graphifyy raises on a single corrupted file
- **THEN** the surrounding files in the same repo are still ingested
- **AND** a structured warning is logged naming the failed file

### Requirement: Auto-confirmation policy for code-graph rows

The `graph_writer` module SHALL assign `state` and numeric `confidence` to graphifyy-extracted rows according to graphifyy's `confidence` label:

- `EXTRACTED` → `state = "confirmed"`, `confidence = 1.0`
- `INFERRED` → `state = "confirmed"`, `confidence = 0.85`
- `AMBIGUOUS` → `state = "candidate"`, `confidence = 0.5`

Every persisted row MUST record `extractor_version` as `graphifyy/{version}` so admins can identify provenance.

#### Scenario: EXTRACTED edge lands confirmed

- **WHEN** the graph writer persists an edge with graphifyy confidence label `EXTRACTED`
- **THEN** the row's `state` is `confirmed` and `confidence` is `1.0`

#### Scenario: AMBIGUOUS edge enters the review queue

- **WHEN** the graph writer persists an edge with graphifyy confidence label `AMBIGUOUS`
- **THEN** the row's `state` is `candidate` and `confidence` is `0.5`

#### Scenario: INFERRED edge is confirmed at a lower confidence

- **WHEN** the graph writer persists an edge with graphifyy confidence label `INFERRED`
- **THEN** the row's `state` is `confirmed` and `confidence` is `0.85`

### Requirement: Graphifyy relation mapping

Graphifyy emits relation names richer than the seeded vocabulary. The `graph_writer` module SHALL map them onto in-vocabulary names before insert:

- `calls` → `calls`
- `imports` → `imports`
- `imports_from` → `imports`
- `contains` → `defined_in`
- `method` → `defined_in`
- `uses` → `uses`

Any graphifyy relation outside this map MUST be skipped with a debug log entry; no edge row is inserted for it.

#### Scenario: contains and method both map to defined_in

- **WHEN** the writer processes graphifyy edges with relations `contains` and `method`
- **THEN** the resulting `relationship_edge` rows both carry `type = "defined_in"`

#### Scenario: imports_from maps to imports

- **WHEN** the writer processes a graphifyy edge with relation `imports_from`
- **THEN** the resulting `relationship_edge` row carries `type = "imports"`

#### Scenario: Unknown relation is dropped

- **WHEN** the writer encounters a graphifyy edge with relation `smells_like` (not in the map)
- **THEN** no edge row is written for that triple
- **AND** the writer continues with subsequent edges

### Requirement: External target concept creation

When graphifyy emits an edge whose target is a string that isn't itself an AST node in the same extraction (e.g., `imports os` where `os` is an external module), the `graph_writer` SHALL create a concept row for that target on the fly so the edge has a valid `to_concept_id`. The on-the-fly concept MUST land at `state = "confirmed"`, `confidence = 1.0`, and dedupe on the normalised target name.

#### Scenario: imports os creates the os concept

- **WHEN** the writer processes an edge `(module, "imports", "os")` and no node with id `"os"` exists in the extraction
- **THEN** a new `opencg.concept` row is created with `name = "os"` and `state = "confirmed"`
- **AND** the edge's `to_concept_id` references the new concept

### Requirement: Symbol identity flows through the catalog

The catalog `metadata` JSONB on chunks produced by `chunk_code_by_symbols` MUST include:

- `symbol_id` (graphifyy's stable per-symbol id derived from the file's **repo-relative path**, e.g., `auth_middleware_verify_token`; it MUST NOT contain a transient or randomly-generated filename stem)
- `symbol_kind` (one of `class`, `function`, `method`, `module`)
- `start_line`, `end_line` (integers)
- `extractor_version` (e.g., `graphifyy/0.8.38`)

These fields MUST be queryable via the existing `GET /entities/{id}` endpoint without changes to the route schema.

The chunk's `entity_id` MUST be derived as `uuid5(_SYMBOL_NS, f"{parent_entity_id}:{symbol_id}")` for symbol-aligned chunks. Because `symbol_id` derives from the stable repo-relative path rather than a transient temp filename, re-ingest of an unchanged file produces stable IDs and upserts are idempotent.

#### Scenario: Symbol chunk metadata is queryable

- **WHEN** an admin calls `GET /entities/{chunk_id}` on a symbol-aligned chunk
- **THEN** the response's `metadata` block contains `symbol_id`, `symbol_kind`, `start_line`, `end_line`, and `extractor_version`

#### Scenario: Idempotent re-ingest of unchanged code

- **WHEN** a repo is re-ingested without changes
- **THEN** existing symbol chunks have unchanged `entity_id` values
- **AND** the catalog rows upsert in place (no duplicate rows)
- **AND** no symbol chunk's `symbol_id` contains a transient temp-file stem
- **AND** the existing graph concepts and edges are unchanged

### Requirement: Graph rows persist via a single transaction

The `graph_writer.write_code_graph` function SHALL wrap all node and edge inserts for a single file in one Postgres transaction acquired from the catalog's connection pool. A failure on any insert MUST roll back every prior insert for that file. The function MUST return `(concepts_written, edges_written)` counts so the caller can record metrics.

#### Scenario: Transaction wraps multi-statement write

- **WHEN** the writer processes one file's nodes and edges
- **THEN** all SQL statements execute inside a single `BEGIN/COMMIT` block
- **AND** the returned counts equal the number of rows successfully inserted

### Requirement: Automatic relationship extraction

Ingestion SHALL run a *concept-and-relationship extractor* on every chunk after the chunk's vector point is upserted to Qdrant. The extractor MUST call a chat model (default: Ollama Cloud `gemma3:4b`) and request a structured JSON output containing `concepts` and `relations`. Concepts MUST be deduped against `opencg.concept` by a normalised `dedupe_key` (Unicode-folded, case-folded, whitespace-collapsed). New concepts AND new edges land in `state = "candidate"`.

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

### Requirement: Review, promote, edit, and delete

The admin API SHALL expose endpoints to list, promote, edit, and delete both candidate concepts and candidate edges. Every state transition MUST write a row to `opencg.graph_audit_log` (separate from the retrieval audit log) capturing `actor`, `target_id`, `target_kind ∈ {concept, edge, vocab}`, `from_state`, `to_state`, `reason`, `at`, and a JSONB `before` / `after` snapshot.

Promotion changes `state` from `candidate` to `confirmed`. Demotion (`confirmed → candidate`) MUST also be supported. Soft-delete (`* → tombstoned`) MUST be supported. `tombstoned` rows MUST NOT appear in traversal or browse responses by default.

#### Scenario: Admin promotes a candidate edge

- **WHEN** an admin posts `POST /graph/edges/{id}/promote` with a reason
- **THEN** the edge's `state` becomes `confirmed`
- **AND** a `graph_audit_log` row is written with `from_state = "candidate"`, `to_state = "confirmed"`, `actor`, `reason`, and the before/after snapshots

#### Scenario: Admin edits an edge type

- **WHEN** an admin posts `PATCH /graph/edges/{id}` with `{type:"defined_in"}` (assume the original type was `mentions`)
- **THEN** the edge's type changes to `defined_in`
- **AND** a `graph_audit_log` row is written with `target_kind = "edge"` and a `before` snapshot containing the old type

#### Scenario: Admin tombstones a concept

- **WHEN** an admin posts `DELETE /graph/concepts/{id}`
- **THEN** the concept's `state` becomes `tombstoned`
- **AND** subsequent `GET /graph/concepts` and `GET /graph/traverse` calls exclude it by default

### Requirement: Graph traversal API

The system SHALL expose `GET /graph/traverse?concept_id=…&types=…&depth=…&limit=…&include_candidates=…` returning the reachable subgraph as `{nodes: [...], edges: [...]}`. `depth` defaults to `2` and is capped at `4`. `limit` defaults to `50` and is capped at `200`. `types` accepts a comma-separated list of vocabulary names; absence means "all types". `include_candidates` defaults to `false`; when `true`, candidate edges and their endpoints are included.

The endpoint MUST execute the traversal via Apache AGE (openCypher) against the `opencg` graph, then hydrate node rows from `opencg.concept` so `name`, `description`, and `state` are present.

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

### Requirement: Concept clustering for review

Deferred. The system SHALL NOT compute or expose concept clusters in this change. A follow-up change (`add-graph-analytics`) introduces clustering and the corresponding admin UI surface.

#### Scenario: Clustering endpoint is absent

- **WHEN** a caller queries any `/graph/clusters` endpoint
- **THEN** the pipeline returns `404 Not Found`

### Requirement: Concept identity and lifecycle

The system SHALL maintain a `opencg.concept` table with `concept_id UUID PRIMARY KEY`, `tenant TEXT NOT NULL`, `name TEXT NOT NULL`, `dedupe_key TEXT NOT NULL`, `description TEXT`, `aliases TEXT[] NOT NULL DEFAULT '{}'`, `state TEXT NOT NULL DEFAULT 'candidate'`, `confidence FLOAT`, `extractor_version TEXT`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`, `tombstoned_at TIMESTAMPTZ`. A UNIQUE constraint on `(tenant, dedupe_key)` enforces dedupe.

The `dedupe_key` MUST be computed as `lower(unaccent(regexp_replace(trim(name), '\s+', ' ', 'g')))` so visually-equivalent surface forms collide.

#### Scenario: Dedupe key catches case and whitespace variants

- **WHEN** the extractor inserts `name = "Prompt Caching"` and later `name = " PROMPT  CACHING "`
- **THEN** the second insert collides on `(tenant, dedupe_key)` and the existing concept is reused
- **AND** the new surface form is appended to `aliases` if it is not already present

#### Scenario: Tombstoned concepts are excluded from browse

- **WHEN** an admin tombstones a concept
- **THEN** `GET /graph/concepts` excludes it by default
- **AND** the concept can be re-included by passing `include_tombstoned=true`

### Requirement: Evidence linkage

Every candidate edge SHALL have at least one row in `opencg.relationship_evidence` linking it to the source chunk's `entity_id` (`opencg.entity`), with a `span TEXT` (optional, the supporting text fragment), `extractor_version`, and `confidence`. Promotion to `confirmed` MUST preserve all evidence rows.

#### Scenario: Evidence row written alongside candidate edge

- **WHEN** the extractor inserts a candidate edge from a specific chunk
- **THEN** a row in `relationship_evidence` is written with the chunk's `entity_id`, the edge's `edge_id`, the `extractor_version`, and the `confidence`

#### Scenario: Multiple chunks support the same edge

- **WHEN** the same `(from, type, to)` triple is extracted from two different chunks
- **THEN** the edge is deduped (one row in `relationship_edge`)
- **AND** two rows exist in `relationship_evidence`, one per chunk

### Requirement: Graph audit log immutability

The `opencg.graph_audit_log` table SHALL be append-only with the same immutability semantics as `opencg.audit_log`: a trigger MUST forbid `DELETE` and forbid `UPDATE` on every column. Partitioning by week MAY be deferred to the operations follow-up change.

#### Scenario: Cannot update a graph audit row

- **WHEN** any code path attempts to `UPDATE` or `DELETE` a `graph_audit_log` row
- **THEN** the database raises an error and the operation fails

### Requirement: Code-graph names derive from the real source path

graphifyy derives node labels and per-symbol ids from the file path it is given. Because the git connector exposes only a file **body** and a **repo-relative path** (`doc.metadata["path"]`) and never an on-disk location, the ingestion service SHALL materialise each code file under its true repo-relative path (e.g. `<tmpdir>/evals/checks.py`) before invoking `graphify.extract([path])` or `chunk_code_by_symbols(path, body)`.

Module/file node labels and per-symbol ids MUST derive from that repo-relative path. The service MUST NOT feed graphifyy a randomly-named or otherwise transient filename whose stem would leak into node labels or symbol identifiers. Any temporary on-disk materialisation MUST be removed after extraction completes, including on the error/fallback path.

#### Scenario: Code-file node reflects its real basename

- **WHEN** the symbol chunker processes `evals/checks.py` from a git ingest whose cloned working tree is no longer on disk
- **THEN** the persisted module/file node is labelled `checks.py` (its real basename)
- **AND** no persisted node label or `symbol_id` contains a transient `tmp`-prefixed random stem

#### Scenario: Repeated extraction of identical content is stable

- **WHEN** the same file body and repo-relative path are extracted twice
- **THEN** the `symbol_id` values produced are identical across both runs
