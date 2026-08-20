# R0 — Grounding Dossier: the verified current state of the openCG knowledge graph

**Model:** Opus 5 thinking @ max
**Scope:** what the code and schema actually do, as of the working tree. No design, no recommendations. Every factual claim cited to `path:line`.

**Exclusion honoured:** did not open `openspec/changes/add-ontology-layer/` or `docs/ontology-council/`.

> **CONTAMINATION DISCLOSURE — read before Round 2.**
> A repository-wide `rg` for `symbol_kind` returned match lines from three files *outside* the named exclusion that contain the draft proposal's text verbatim: `tools/explainer/content/07-ontology.md`, and the generated snapshots `docs/explainer/versions/0002-2026-08-06.json` and `0003-2026-08-07.json` (the explainer generator inlines proposal prose into its JSON snapshots). R0 saw fragments of the draft's design language, quoted none of it, drew no design conclusions from it, and excluded those files.
> **The council MUST add these paths to the exclusion list**, plus `docs/explainer/index.html`, which embeds the same snapshots (`docs/explainer/index.html:776`).

---

## 0. Correction to the brief's premise

The brief said a `concept` row "is only a name, a dedupe key, a description, an aliases array, a review state, and a confidence score. Nothing records that `parse_config` is a function."

**That is not what the code does.** `opencg.concept` has had a `symbol_kind TEXT` column since the graph schema landed. It is written on the code path, read on every graph query, carried in both wire-type mirrors, and rendered in the admin UI.

```62:65:infra/postgres/init/040_graph.sql
  -- Code-specific: graphifyy's stable per-symbol id (e.g.
  -- module.path.ClassName.method_name). Optional; null for non-code concepts.
  symbol_id         TEXT,
  symbol_kind       TEXT,
```

- Written: `services/ingestion/src/opencg_ingestion/graph_writer.py:126` computes `kind = _kind_from_label(label)`, binds at `:132`/`:153`, `COALESCE` preserve-on-conflict at `:140`.
- Read: `services/pipeline/src/opencg_pipeline/storage/graph.py:81` (`list_concepts`), `:105` (`get_concept`), `:125` (neighbour peers), `:299` (traversal hydration).
- Wire types: `packages/shared-py/src/opencg_shared/types.py:213-214`; `packages/shared/src/index.ts:199-200`.
- Rendered: `services/admin-ui/src/components/ConceptDetail.tsx:75` prints `{state} · {symbol_kind}`.

**The accurate statement of the gap is narrower:** a kind field exists and is plumbed end-to-end, but it is populated by a three-branch string heuristic, only on the code path, with no constrained value set, no database constraint, no index, and no consumer that filters or aggregates on it.

---

## 1. Graph schema — every table, column, constraint, index, trigger

Two init scripts: `infra/postgres/init/040_graph.sql` (127 lines) and `050_graph_audit.sql` (95 lines). The `SET search_path = ag_catalog, "$user", public;` at `040_graph.sql:14` is required because Apache AGE's bundled `00-create-extension-age.sql` runs first.

### 1.1 `opencg.relationship_vocab`

```20:27:infra/postgres/init/040_graph.sql
CREATE TABLE opencg.relationship_vocab (
  name          TEXT PRIMARY KEY,
  description   TEXT NOT NULL,
  inverse       TEXT,
  directed      BOOLEAN NOT NULL DEFAULT TRUE,
  deprecated_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

No indexes beyond the PK. No triggers.

**The exact seeded vocabulary — all ten rows** (`040_graph.sql:32-43`):

| `name` | `description` | `inverse` | `directed` |
|---|---|---|---|
| `depends_on` | A requires B to function (semantic dependency, not necessarily a code call) | `depended_on_by` | TRUE |
| `defined_in` | A is declared inside B (concept membership; e.g., a function defined in a file) | `defines` | TRUE |
| `supersedes` | A replaces B (A is the newer version of the same concept) | `superseded_by` | TRUE |
| `mentions` | A references B by name without invoking or depending on it | `mentioned_by` | TRUE |
| `related_to` | A and B share a concept or category (symmetric) | `related_to` | **FALSE** |
| `causes` | A leads to B happening (causal) | `caused_by` | TRUE |
| `derived_from` | A is a derivative or extension of B | `parent_of` | TRUE |
| `calls` | Function A invokes function B (extracted from a call expression) | `called_by` | TRUE |
| `imports` | Module/file A imports symbol or module B | `imported_by` | TRUE |
| `uses` | A references B's identifier without invoking it (read or pass-through) | `used_by` | TRUE |

First seven labelled in-source as "domain-of-discourse relations the LLM extractor produces"; last three as "Code-structure relations from graphifyy (tree-sitter, deterministic)" (`:29-31`, `:40`).

**`inverse` and `directed` are dead columns.** Searching `services/` finds them only in CRUD SQL (`storage/graph.py:49, 616, 622-623, 669, 675-676`), Pydantic request bodies (`graph/routes.py:35-36, 41-42`), and a Storybook fixture (`VocabRow.stories.tsx:3`). No traversal, extraction, validation, or query code reads either. `related_to` being `directed = FALSE` has no effect anywhere.

### 1.2 `opencg.concept`

```49:70:infra/postgres/init/040_graph.sql
CREATE TABLE opencg.concept (
  concept_id        UUID PRIMARY KEY,
  tenant            TEXT NOT NULL,
  name              TEXT NOT NULL,
  dedupe_key        TEXT NOT NULL,
  description       TEXT,
  aliases           TEXT[] NOT NULL DEFAULT '{}',
  state             TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate','confirmed','tombstoned')),
  confidence        FLOAT,
  extractor_version TEXT,
  symbol_id         TEXT,
  symbol_kind       TEXT,
  source_entity_id  UUID,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  tombstoned_at     TIMESTAMPTZ
);
```

Indexes (`:72-74`): `concept_dedupe_uq UNIQUE (tenant, dedupe_key)`, `concept_state_ix (tenant, state)`, `concept_symbol_ix (tenant, symbol_id) WHERE symbol_id IS NOT NULL`.

**No index on `symbol_kind`. No `CHECK` constraint on `symbol_kind`.** Free text.

`source_entity_id UUID` at `:66` carries **no foreign key**, unlike `relationship_evidence.entity_id` which does (`:108`). No triggers.

### 1.3 `opencg.relationship_edge`

```80:92:infra/postgres/init/040_graph.sql
CREATE TABLE opencg.relationship_edge (
  edge_id           UUID PRIMARY KEY,
  tenant            TEXT NOT NULL,
  type              TEXT NOT NULL REFERENCES opencg.relationship_vocab(name),
  from_concept_id   UUID NOT NULL REFERENCES opencg.concept(concept_id),
  to_concept_id     UUID NOT NULL REFERENCES opencg.concept(concept_id),
  state             TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate','confirmed','tombstoned')),
  confidence        FLOAT NOT NULL DEFAULT 0.0,
  extractor_version TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  tombstoned_at     TIMESTAMPTZ
);
```

Indexes (`:94-99`): `relationship_edge_triple_uq UNIQUE (tenant, from_concept_id, type, to_concept_id)`, `(state, confidence DESC)`, `(from_concept_id)`, `(to_concept_id)`. No triggers.

**No self-loop prevention** at the database level. The admin UI's `buildGraphModel` discards them for rendering only (`services/admin-ui/src/app/graph/graph-model.ts:40`).

### 1.4 `opencg.relationship_evidence`

```105:113:infra/postgres/init/040_graph.sql
CREATE TABLE opencg.relationship_evidence (
  evidence_id       BIGSERIAL PRIMARY KEY,
  edge_id           UUID NOT NULL REFERENCES opencg.relationship_edge(edge_id) ON DELETE CASCADE,
  entity_id         UUID NOT NULL REFERENCES opencg.entity(entity_id),
  span              TEXT,
  extractor_version TEXT,
  confidence        FLOAT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes on `(edge_id)` and `(entity_id)` (`:115-116`). No uniqueness — repeated ingests append duplicate evidence rows.

### 1.5 `opencg.graph_audit_log`

```11:23:infra/postgres/init/050_graph_audit.sql
CREATE TABLE opencg.graph_audit_log (
  id          BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor       TEXT NOT NULL,
  tenant      TEXT NOT NULL,
  target_kind TEXT NOT NULL CHECK (target_kind IN ('concept','edge','vocab')),
  target_id   TEXT NOT NULL,
  from_state  TEXT,
  to_state    TEXT,
  reason      TEXT,
  before      JSONB,
  after       JSONB
);
```

Three descending-time indexes (`:25-30`). The **only trigger in the graph schema** is `graph_audit_log_no_modify` (`:48-50`) running `opencg.graph_audit_log_immutable()` (`:35-46`), raising on `UPDATE` and `DELETE`. The `CHECK` on `target_kind` is a **closed three-value set** — a fourth audit target kind needs a migration.

### 1.6 Apache AGE label bootstrap

`050_graph_audit.sql:59-90` runs `LOAD 'age'` and a `DO` block creating exactly **one vertex label, `Concept`** (`:71-74`), and **one edge label per `relationship_vocab` row** (`:78-88`).

```52:58:infra/postgres/init/050_graph_audit.sql
-- Apache AGE label types for the knowledge graph. We use AGE's openCypher
-- only as a queryable index over the same edges; the source of truth lives
-- in opencg.relationship_edge. Bootstrapping the labels here lets the
-- traversal endpoint issue Cypher without first checking-and-creating.
```

**The graph's only typed dimension in AGE is the edge label. Every node carries the single label `Concept`.**

### 1.7 Database-enforced vs application-enforced

| Rule | Enforced by |
|---|---|
| Edge type must exist in vocabulary | **Database** — FK (`040_graph.sql:83`) |
| Edge endpoints must be real concepts | **Database** — two FKs (`:84-85`) |
| `state ∈ {candidate, confirmed, tombstoned}` | **Database** — `CHECK` on both tables (`:59`, `:86`) |
| One edge per `(tenant, from, type, to)` | **Database** — unique index (`:94-95`) |
| One concept per `(tenant, dedupe_key)` | **Database** — unique index (`:72`) |
| Audit rows immutable | **Database** — trigger (`050_graph_audit.sql:48-50`) |
| `dedupe_key` normalisation | **Application only** — three separate `_normalize` impls, see §2.4 |
| Edge type must not be *deprecated* | **Application, one path only** — `_assert_active_vocab` (`storage/graph.py:984-995`) called from `patch_edge` (`:552`) and nowhere else. Neither writer checks it. |
| `symbol_kind` value set | **Nothing** — no constraint, no validation, no enum |
| Node type / class of a concept | **Nothing** beyond free-text `symbol_kind` |
| Which relation types may connect which kinds | **Nothing** |

---

## 2. The two extraction paths

### 2.1 Prose path — `services/pipeline/src/opencg_pipeline/graph/extract.py`

**The prompt, verbatim.** Built by `build_prompt(text, vocabulary)` (`:89-111`). `vocab_str` is `", ".join(sorted(vocabulary))` (`:96`), so the model receives the ten names alphabetised.

System message (`extract.py:97-107`):

```text
You are a careful information extractor. From the user's text, produce ONLY a JSON object with two arrays:
  "concepts": [{"name", "description"?, "aliases"?[]}],
  "relations": [{"from","relation","to","evidence_span"?,"confidence"}].
Each relation `confidence` is a number in [0,1].
Use relation names from this vocabulary only: calls, causes, defined_in, depends_on, derived_from, imports, mentions, related_to, supersedes, uses.
Concept names are short noun phrases (1-4 words). Be conservative — only emit relations the text clearly supports. Output JSON only, no commentary.
```

User message: stripped chunk text, hard-truncated at 8,000 characters with `\n…[truncated]` appended (`:108-110`).

Four things matter:

1. **The model is never told what kinds of thing exist.** Ten relation names and "short noun phrases (1-4 words)". Nothing says a concept could be a service, topic, function, or person.
2. **The model is never told which relations may connect which things.** `calls`, `imports`, `uses` — seeded *specifically for graphifyy's tree-sitter output* (`040_graph.sql:40`) — are offered to `gemma3:4b` reading Markdown, because `load_vocabulary` selects every non-deprecated row without a source filter (`text_graph_writer.py:246-248`).
3. **The declared `_RESPONSE_SCHEMA` is never sent to the model.** `extract.py:41-71` defines a JSON Schema; `extract_for_chunk` passes it as `response_schema=` (`:211`); but `OllamaChat.chat` uses it only as a boolean: `if response_schema is not None: body["format"] = "json"` (`providers.py:168-169`). The schema object is discarded. `docs/EXTRACTOR_PROMPT.md:22-56` reproduces it under "## Response schema" without noting it is not transmitted.
4. **No system-prompt content is version-pinned.** `current_extractor_version` returns `f"text-extractor/v1/{model}"` (`reextract.py:28-29`) — a hand-bumped `v1`, not a prompt hash.

**Parsing** (`parse_response`, `:120-146`): strips fences, takes first `{` to last `}`, `json.loads`, `ExtractionResult.model_validate`. Returns `None` on any failure. No repair or retry.

**Filtering** (`filter_result`, `:149-181`) does exactly three things:
- Drops relations whose `relation` is not in the vocabulary set (`:166-168`) → `dropped_unknown_vocab`.
- Drops relations with `confidence < min_confidence` (`:169-171`) → `dropped_low_confidence`.
- Drops relations with an empty normalised endpoint name (`:172-173`) — silently, uncounted.
- **Keeps every concept unconditionally**: "Concepts that no surviving relation references are still kept — they may be standalone nouns worth recording" (`:158-159`, `:175-176`).

**No check that the two endpoints of a relation are semantically compatible, because there is nothing to check them against.**

**Thresholds.** `min_confidence` defaults to `0.6` in the signature (`:191`), config model (`config.py:59`), and checked-in YAML (`opencg.yaml:56`). `timeout_seconds` `30.0` in all three. `chat_qps` exists in config (`config.py:61`, `opencg.yaml:58`) and is **never read by any code**.

**Telemetry.** `STAGE_LATENCY` under `stage="graph_extract_text"` (`:230`); `record_stage_tokens` (`:231-238`); span `pipeline.graph_extract_text` (`:204`, `:239-243`); `EXTRACTOR_EDGES.labels(relation=…, state="candidate")` — **state hardcoded** (`:261-265`); `EXTRACTOR_ERRORS.labels(reason=…)` for `timeout`/`provider`/`parse`.

**Failure contract.** Timeout, transport error, and parse failure all *raise* to the caller (`:222`, `:226`, `:254`).

### 2.2 Prose writer — `text_graph_writer.py`

`write_text_graph` (`:46-185`), one transaction (`:65-66`).

- Concepts: `INSERT … ON CONFLICT (tenant, dedupe_key) DO UPDATE` merging `description` via `COALESCE`, unioning `aliases` (`:73-91`). `state = "candidate"` (`:98`), **`confidence = None`** (`:99`). Columns written: `concept_id, tenant, name, dedupe_key, description, aliases, state, confidence, extractor_version, source_entity_id` — **`symbol_id` and `symbol_kind` are not in the list.** Every prose concept has both null forever.
- `RETURNING concept_id::text, state` (`:90`) and the returned id is used, so a prose concept colliding with an existing code concept **adopts the code concept's identity**. Locked by `test_uses_authoritative_concept_ids_after_dedupe_conflict` (`test_text_graph_writer.py:135-182`).
- Endpoints not present as declared concepts are created by `_ensure_concept` (`:188-232`): `state = "candidate"`, `confidence = None`, again no `symbol_*`.
- Edges: `state = "candidate"` (`:157`), `confidence` from the model (`:158`), `ON CONFLICT … DO UPDATE SET confidence = GREATEST(existing, new)` (`:146-149`). The conflict clause does **not** touch `state`, so an existing `confirmed` edge stays confirmed on re-extract.
- Evidence row per edge with `span = r.evidence_span` (`:172-183`).

Docstring states the policy:

```5:9:services/ingestion/src/opencg_ingestion/text_graph_writer.py
- Concepts and edges land in `state = "candidate"` by default — the LLM
  output is non-deterministic, so reviewers should triage before edges
  enter traversal results. (Configurable per-call via `auto_confirm`.)
```

The parenthetical is **stale**: `write_text_graph` has no `auto_confirm` parameter (`:46-53`).

### 2.3 Code path — `graph_writer.py`

Runs on graphifyy's `{nodes, edges}`. Never calls a model.

**Node selection** (`:100-104`): `_origin == "ast"` **and** `file_type == "code"`. **The module/file node is not excluded here**, unlike in the chunker (§3.2).

**Kind derivation** — the entire type-inference logic on the code path:

```80:85:services/ingestion/src/opencg_ingestion/graph_writer.py
def _kind_from_label(label: str | None) -> str | None:
    if not label:
        return None
    if label.endswith("()"):
        return "method" if label.startswith(".") else "function"
    return "class"
```

Three branches over a display string. The `else` returns `"class"` for **everything** not ending in `()`. The module node's label is the filename — the repo's own fixture uses `{"id": "mod", "label": "mod.py", …}` (`test_graph_writer.py:274`) — so **every file/module node in the graph is recorded as `symbol_kind = "class"`.** This function can **never** return `"module"`, though `"module"` is one of the four values the archived spec mandates (§8.2).

**Relation mapping** (`:44-51`), six entries, unmapped skipped at debug (`:167-171`):

| graphifyy relation | stored `type` |
|---|---|
| `calls` | `calls` |
| `imports` | `imports` |
| `imports_from` | `imports` |
| `contains` | **`defined_in`** |
| `method` | **`defined_in`** |
| `uses` | `uses` |

`contains` and `method` collapse into one type. Locked by `test_relations_map_to_vocabulary` (`test_graph_writer.py:211-241`).

**State/confidence** (`:54-58`), keyed on graphifyy's confidence *label*:

```54:58:services/ingestion/src/opencg_ingestion/graph_writer.py
_CONFIDENCE_MAP: dict[str, tuple[str, float]] = {
    "EXTRACTED": ("confirmed", 1.0),
    "INFERRED":  ("confirmed", 0.85),
    "AMBIGUOUS": ("candidate", 0.5),
}
```

Unrecognised labels fall back to `("confirmed", 1.0)` (`:212-214`) — an unknown graphifyy label is treated as maximally trustworthy.

**Concepts** land `state = "confirmed"`, `confidence = 1.0` unconditionally (`:149-150`), regardless of edge confidence labels. The `ON CONFLICT` updates only `symbol_id, symbol_kind, extractor_version, updated_at` (`:138-142`), and `symbol_kind` is `COALESCE`-preserved — **the first classification a concept ever receives is permanent**, and `patch_concept` cannot edit it (§6.3).

**External import targets** (`:172-208`): when an edge target is not among extracted nodes, a concept is minted with `state = "confirmed"`, `confidence = 1.0`, and **no `symbol_id`, no `symbol_kind`** (`:183-187`). So `os`, `re`, `httpx` land as untyped confirmed concepts.

**Extractor version:** `f"graphifyy/{graphify.__version__}"` (`:76-77`). Pinned `graphifyy>=0.8,<0.9` (`services/ingestion/pyproject.toml:15`).

### 2.4 Three (four) independent `_normalize` implementations

- `graph_writer.py:61-65` — NFKC, strip, lower, collapse whitespace
- `text_graph_writer.py:32-35` — byte-identical
- `extract.py:114-117` — byte-identical (emptiness checks only)

And a fourth, **different**, on the admin edit path: `storage/graph.py:943-944` — `" ".join(name.strip().lower().split())`, omitting the NFKC fold. Renaming via `PATCH /graph/concepts/{id}` can produce a `dedupe_key` the ingest writers would not produce for the same name. The schema comment promises `lower(unaccent(...))` (`040_graph.sql:53`); **none of the four does accent-folding.** `café` and `cafe` do not collide.

### 2.5 Where each path is invoked

Single dispatch point: `ingest_documents` (`pipeline_runner.py:50-243`).

Per document (`:95`): insert parent entity (`:104-115`) → `code = is_code_path(path)` (`:117-118`) → branch.

- **Code** (`:120-124`): `_extract_code` (`:284-317`) materialises the body under its real repo-relative path (`:259-281`), calls `gex.extract([use_path], parallel=False)` **and** `chunk_code_by_symbols(use_path, doc.body)` — so graphifyy parses each code file **twice** per ingest (`:308`, and inside `chunking.py:170`). On exception: falls back to `chunk_text` and returns `None` for the graph (`:312-315`).
- **Non-code** (`:126-127`): `chunk_text(doc.body)`, `code_graph = None`.

Per chunk (`:129`): catalog insert → embed → Qdrant upsert → **prose extraction gated on `if not code`** (`:189-214`), wrapped in bare `except Exception` logging at INFO (`:208-214`).

After the chunk loop (`:218-229`): `write_code_graph`, wrapped in `except Exception` logging at WARNING.

**The two paths are mutually exclusive per file.** A `.py` file gets graphifyy edges and zero LLM calls; a `.md` file gets LLM candidate edges and zero graphifyy edges (`:184-188`). Gate: `if cfg.providers.extraction.enabled and chat_cfg is not None` (`:76`); a vocabulary-load failure disables chat entirely (`:83-88`).

**Divergence:** the `re-extract` CLI does **not** replicate the `if not code` gate. `_list_chunks` (`reextract.py:109-146`) selects every chunk where `parent_entity_id IS NOT NULL AND tombstoned_at IS NULL` — no `metadata ? 'symbol_id'` exclusion. So `opencg-ingest re-extract` feeds **code symbol chunks to `gemma3:4b`** and writes `candidate` concepts/edges alongside the deterministic ones. Nothing in the schema records that an edge came from a code chunk except the `extractor_version` string.

---

## 3. Metadata a type system could already use

### 3.1 Chunk metadata does carry `symbol_kind`

`chunk_code_by_symbols` (`chunking.py:148-311`) writes `symbol_kind` at three sites: merged (`:242`), oversized-split (`:272`), normal (`:301`). Alongside `symbol_id`, `symbol_ids`, `start_line`, `end_line`, `extractor_version`, `parent_symbol_id`, `split`.

`_symbol_kind` (`:126-139`) is a **fourth** near-copy of the heuristic, differing from `graph_writer._kind_from_label`:

```126:139:services/ingestion/src/opencg_ingestion/chunking.py
def _symbol_kind(label: str) -> str:
    """Coarse classifier from graphifyy's `label` field.

    graphifyy emits labels like "Greeter", ".__init__()", ".greet()",
    "greet_template()". A method-style label starts with "." and ends with
    "()"; a free function ends with "()" but does not start with "."; a
    class is bare. This is a heuristic — good enough for chunk metadata
    until we wire in graphifyy's own kind hints.
    """
    if not label:
        return "module"
    if label.endswith("()"):
        return "method" if label.startswith(".") else "function"
    return "class"
```

Differences: empty label → `"module"` here, `None` there. This one can also emit `"merged"` (`:242`), a fifth value produced only by the chunker.

**The docstring is the code's own admission that graphifyy has kind information it is not using**: *"until we wire in graphifyy's own kind hints"* (`:133`).

**Could not verify:** `graphifyy` is not installed in this working tree, so R0 could not inspect its node schema or confirm whether it exposes first-class kind hints. What openCG observes of a graphifyy node: `id`, `label`, `file_type`, `_origin`, `source_file`, `source_location` (a `"L42"` string, parsed at `chunking.py:116-123`) — per fixtures at `test_graph_writer.py:83-90`. Edges carry `source`, `target`, `relation`, `confidence`, `source_location` (`:117-123`). **The council should close this against the installed package.**

### 3.2 What is discarded, precisely

**(a) The chunker's `symbol_kind` never reaches the graph writer.** `_extract_code` returns `(chunks, graphify_result)` (`pipeline_runner.py:317`); `write_code_graph` receives only `graphify_result` (`:220-225`) and re-derives kind from `node["label"]`. The two derivations are independent and not identical. The chunker's `"module"` and `"merged"` are structurally unable to reach `concept.symbol_kind`.

**(b) The module/file node is filtered out of chunking but not out of the graph.**

```180:185:services/ingestion/src/opencg_ingestion/chunking.py
    # Drop the top-level module node — its body is the whole file, which
    # would duplicate every symbol chunk inside it.
    symbol_nodes = [n for n in raw_nodes if (n.get("label") or "") not in ("", path.stem + path.suffix)]
    # graphifyy labels the module-level node as the bare filename or the
    # module stem. Filter both shapes.
    symbol_nodes = [n for n in symbol_nodes if n.get("source_location") != "L1" or _symbol_kind(n.get("label", "")) != "module"]
```

`write_code_graph`'s node filter (`graph_writer.py:100-104`) has no equivalent. File nodes *are* concepts, classified `"class"`.

**(c) `symbol_kind` never reaches the vector index.** The Qdrant payload (`pipeline_runner.py:163-175`) carries `tenant, entity_id, parent_entity_id, source, source_uri, title, text, classification, chunk_index`, plus `symbol_id` only if present:

```174:175:services/ingestion/src/opencg_ingestion/pipeline_runner.py
        if ch.metadata.get("symbol_id"):
            payload["symbol_id"] = ch.metadata["symbol_id"]
```

`symbol_kind`, `start_line`, `end_line`, `parent_symbol_id` are not copied. `VectorIndex._build_filter` (`storage/vector.py:147-156`) builds Qdrant `must` conditions from arbitrary payload keys — filtering vector search by kind is one payload key away mechanically, but the key is not written.

### 3.3 Where `symbol_kind` *is* stored, and how queryable

Full chunk metadata reaches Postgres: `meta = {**doc.metadata, **ch.metadata, "chunk_index": ch_index}` (`pipeline_runner.py:134`) → `metadata=meta` (`:156`) → `json.dumps` into `opencg.entity.metadata JSONB` (`storage/catalog.py:88`). Readable via `GET /entities/{id}` (`catalog.py:155-174`).

But `opencg.entity` has **no GIN index on `metadata`** (`020_catalog.sql:27-32` lists six indexes, none on metadata). Any `metadata->>'symbol_kind' = 'function'` predicate is a sequential scan. The only JSONB metadata query in the codebase is a `NULLS LAST` sort on `(metadata->>'chunk_index')::int` (`catalog.py:190`) and the smoke test's `chunk.metadata ? 'symbol_id'` existence check (`tests/smoke/run.sh:331`).

**Kind information exists in two places and is efficiently queryable in neither.**

---

## 4. Traversal and query

### 4.1 `GraphStore.traverse` — how it actually works

`storage/graph.py:230-347`. Five steps:

1. **Existence check** (`:241-252`): start concept must exist, be in-tenant, non-tombstoned. Else `None` → 404.
2. **Type validation** (`:253-266`): every supplied name must exist in `relationship_vocab` (`:254-260`) or `ValueError` → 400 (`routes.py:137-138`). Names pass `_validated_relation` against `^[a-z][a-z0-9_]*$` (`:928-931`) before interpolation as `:a|b|c` (`:264-266`). **Existence-only, not active-only** — a deprecated type is still an accepted filter.
3. **AGE candidate generation** (`:276-292`):

```282:286:services/pipeline/src/opencg_pipeline/storage/graph.py
                MATCH (start:Concept {{concept_id: $concept_id}})
                      -[edges{relation_pattern}*1..{depth}]-
                      (peer:Concept)
                RETURN DISTINCT peer.concept_id
                LIMIT $candidate_limit
```

`candidate_limit = min(limit * 10, 2000)` (`:273`). **This pattern is undirected** — `-[…]-`. There is **no state predicate**, so tombstoned and candidate AGE edges both contribute to reachability.

4. **Node hydration** (`:296-311`): `SELECT concept_id, tenant, name, state, confidence, aliases, symbol_id, symbol_kind, updated_at, tombstoned_at … WHERE tenant = $1 AND concept_id = ANY($2::uuid[]) AND state <> 'tombstoned'`. **`description` is not selected** (§8.3).
5. **Edge fetch and Python BFS** (`:313-337`): edges fetched from Postgres with both endpoints in the hydrated set, `state = ANY($3)` (`:269`), optional type filter. Then `_reachable_ids` (`:947-981`) does the authoritative traversal — a **Python breadth-first search**:

```957:962:services/pipeline/src/opencg_pipeline/storage/graph.py
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            source = str(edge["from_concept_id"])
            target = str(edge["to_concept_id"])
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)
```

Both directions inserted. `limit` truncates mid-BFS (`:976-977`); `limit <= 1` short-circuits (`:954-955`).

**What Apache AGE is actually for.** Per the schema comment, "a queryable index over the same edges" (`050_graph_audit.sql:53-55`). Per the code, narrower still: it produces a bounded set of candidate concept IDs, and every semantically meaningful decision — state filtering, tenant filtering, tombstone exclusion, type filtering, reachability, ordering, `limit` — is recomputed in Postgres and Python. **The AGE result is not returned to the caller in any form.**

### 4.2 The complete filter surface

`GET /graph/traverse` accepts exactly four parameters besides `concept_id` (`routes.py:119-127`):

| Parameter | Type | Default | Cap | Enforced at |
|---|---|---|---|---|
| `types` | comma-separated vocab names | all | — | `_csv` (`routes.py:51-52`) + vocab existence (`graph.py:254-263`) |
| `depth` | int | 2 | `ge=1, le=4` | FastAPI `Query` (`routes.py:124`) |
| `limit` | int | 50 | `ge=1, le=200` | FastAPI `Query` (`routes.py:125`) |
| `include_candidates` | bool | `false` | — | `routes.py:126` → `graph.py:269` |

That is the entire query language. **No direction parameter, no node-side filter of any kind, no confidence threshold, no `extractor_version` filter, no evidence-count filter, no source filter, no sort control, no pagination.** `TraverseRequest` matches exactly (`types.py:252-257`; `index.ts:238-244`), as does the MCP tool schema (`tools.ts:70-81`).

### 4.3 Node hydration on other read paths

- `list_concepts` (`:56-95`): filters `tenant`, `states`, `include_tombstoned`, `search` — the latter a bare `name ILIKE '%…%'` (`:73-75`) which **does not search `aliases` or `description`**. Ordered `updated_at DESC`. Returns `symbol_id`/`symbol_kind` (`:81`).
- `get_concept` (`:97-184`): full row including `description`, `dedupe_key`, `extractor_version`, `source_entity_id`, `symbol_id`, `symbol_kind` (`:103-106`), plus neighbours with aggregated `evidence_entity_ids` (`:115-146`). Bucketed by `data[f"neighbours_{n['state']}"]` (`:183`) — a dynamic key safe only because the SQL excludes tombstoned (`:139-140`).
- `list_edges` (`:186-228`): filters `state` (single value) and `type`. Ordered `confidence DESC, created_at DESC`.

---

## 5. The retrieval path — the graph is not consulted

**Confirmed: `/retrieve` never reads the knowledge graph.**

`app.py:117-249` is the whole handler. It binds five things off `app.state` at `:119-124`: `cfg`, `tracer`, `catalog`, `audit`, `vector`, `embeddings`. `app.state.graph` — the `GraphStore` constructed at `:49` and connected at `:65` — **is not among them**. `GraphStore`, `traverse`, `concept`, and `relationship_edge` appear nowhere in the function body.

What retrieval does:

1. **`identity.run(req)`** (`:138`) — stage `"identity"`.
2. **`hybrid_retrieval.run(...)`** (`:146-153`) — `stages/hybrid_retrieval.py:33-105`. Two legs in `asyncio.gather` (`:56-58`): dense (embed query, `vector.search(sources=None, …)` — no filter argument, `:50`) and lexical (`catalog.lexical_search`, `plainto_tsquery('simple', …)` with a `%` trigram fallback, `catalog.py:237-276`). Fused by `reciprocal_rank_fusion` (`:62`), re-sorted, truncated to `top_k` (`:96`).
3. **`assemble.run(...)`** (`:181-186`) — `stages/assemble.py:28-60`. A role→classification allow-list (`:14-18`) and a greedy token budget. Nothing graph-aware.
4. **Build `ContextFragment`s and write the audit row** (`:195-235`).

Two further facts:

- **The audit row hardcodes the absence.** `"intent_plan": {"mvp": "hybrid_only"}` (`app.py:221`).
- **`RetrievalRequest.filters` is dead.** Declared at `types.py:25`, mirrored in the MCP tool schema (`tools.ts:40`), forwarded by the MCP client (`tools.ts:183`) — and never read in `app.py`. `hybrid_retrieval.run` has no `filters` parameter (`:33-41`), and its `vector.search` call omits the `filters=` kwarg that `VectorIndex.search` accepts (`vector.py:59`). Whatever a caller passes is silently discarded.

**MCP surface.** Five tools advertised (`tools.ts:29-97`); two live. `opencg/retrieve_for_context` → `POST /retrieve`. `opencg/traverse_graph` → `GET /graph/traverse` (`tools.ts:139-162`). Entirely separate calls with no shared state — an MCP client wanting graph-informed retrieval must orchestrate both itself, and `retrieve_for_context` returns `entity_id`s while `traverse_graph` takes a `concept_id`, **with no endpoint that maps between them**.

**The spec agrees with the code.** `openspec/specs/retrieval-pipeline/spec.md` has seven requirements; **none requires `/retrieve` to consult the graph.** `README.md:13` describes "catalog/graph enrichment" as vision; `README.md:209` describes what is built: "four stages: identity → hybrid retrieval … → assemble → return".

---

## 6. Admin surfaces

### 6.1 Endpoints — `graph/routes.py`, prefix `/graph`

Reads: `GET /vocab` (`:55`), `GET /concepts` (`:60`), `GET /concepts/{id}` (`:88`), `GET /edges` (`:99`), `GET /traverse` (`:119`).

Writes: `POST /concepts/{id}/promote` (`:163`), `/demote` (`:170`), `DELETE /concepts/{id}` (`:177`), `PATCH /concepts/{id}` (`:184`), `POST /concepts/merge` (`:204`), `POST /edges/{id}/promote` (`:238`), `/demote` (`:245`), `DELETE /edges/{id}` (`:252`), `PATCH /edges/{id}` (`:259`), `POST /vocab` (`:277`), `PATCH /vocab/{name}` (`:294`), `POST /vocab/{name}/deprecate` (`:308`).

Every write derives `actor` from `cfg.identity.principal` — the stubbed `local-dev` (`opencg.yaml:9`). Every state transition writes a `graph_audit_log` row via `_write_audit` (`graph.py:998-1027`), with an idempotency short-circuit skipping the audit row when state is unchanged (`:368-369`, `:485-486`).

**There is no authentication on any of these routes.** `app.py` registers no middleware, no dependency, no guard.

### 6.2 `POST /graph/vocab` creates an AGE edge label at runtime

`create_vocabulary` (`graph.py:597-647`) inserts the row then calls `ag_catalog.create_elabel('opencg', $1)` (`:626-634`) in the same transaction. AGE labels stay in sync for additions. Deprecation does not drop the label (`:693-729`).

### 6.3 What a reviewer can and cannot edit

```414:416:services/pipeline/src/opencg_pipeline/storage/graph.py
        allowed = {key: value for key, value in changes.items() if key in {"name", "description", "aliases"}}
        if not allowed:
            raise ValueError("no editable concept fields supplied")
```

Three fields. **`symbol_kind` is not editable through any API.** `ConceptPatch` (`routes.py:18-22`) exposes only those three plus `reason`. `patch_edge`'s allow-list is `{"type", "from_concept_id", "to_concept_id"}` (`graph.py:534-538`).

`merge_concepts` (`:731-925`) re-points edges, dedupes against the unique triple by migrating evidence and deleting the loser (`:788-822`), unions aliases (`:846-857`), tombstones sources with one audit row each (`:890-924`). It does **not** reconcile `symbol_id`/`symbol_kind` — the target keeps what it had, the source's values are lost.

### 6.4 Admin UI `/graph`

`services/admin-ui/src/app/graph/page.tsx` — four tabs, `map` default (`:23`): `map`, `concepts`, `candidates`, `vocabulary` (`:14-19`). Client depth clamped to `1..3` (`:24`) despite the API cap being 4.

- **Map** — `GraphExplorer.tsx`, `react-force-graph-2d`. Nodes coloured **by review state only**: `candidate` amber, else emerald (`:168`, `COLORS` `:17-24`). Node radius encodes **degree**, not kind (`:162`). Controls: depth 1/2/3, candidates toggle, concept search (`:227-251`). `buildGraphModel` (`graph-model.ts:32-55`) projects to `{id, name, state, degree, isFocus}` — **`symbol_kind` is not in `GraphNode`** (`:3-9`), so it cannot reach the canvas.
- **Concepts** — `ConceptRow.tsx`, three columns: name + aliases, state, confidence (`:9-28`). **No kind column.**
- **Candidate review** — `CandidateEdgeRow` per candidate edge with evidence links (`page.tsx:52`).
- **Vocabulary** — `VocabRow` plus a create form (`page.tsx:57-58`).
- **Detail panel** — `ConceptDetail.tsx:75` is the **only** place `symbol_kind` surfaces in the UI, as a suffix on the state line.

Client→pipeline traffic goes through Next route handlers (`src/app/api/proxy/graph/[...path]/route.ts`).

---

## 7. The corpus

### 7.1 What the connector accepts (fact)

One connector: git (`connectors/git.py`). `ingest_repo` shallow-clones (`--depth 1`, `:64-68`). Discovery is the **union** of two sets (`_discover_files`, `:78-99`):

- `graphify.collect_files(repo_path)` — "80+ file extensions across 28 tree-sitter-supported languages" honouring `.graphifyignore` (`:4-6`, `:81-84`).
- An `rglob` over 13 hardcoded text extensions (`TEXT_EXTS`, `:31-35`): `.md .markdown .rst .txt .yaml .yml .toml .json .ini .html .css .scss .sass`.

Deduped with "Code path wins" (`:92-98`). Skips files over `MAX_FILE_BYTES = 1_000_000` (`:37`), non-UTF-8, unreadable (`:123-132`).

Dispatch by extension (`is_code_path`, `chunking.py:99-109`): `False` if the suffix is in `_NON_CODE_EXTS_IN_DISPATCH` — `.md .markdown .rst .txt .yaml .yml .toml .json .ini .html .htm` (`:92-96`) — else `True` iff the suffix is in `gex._DISPATCH`. **Asymmetry:** `.css`, `.scss`, `.sass` are in `TEXT_EXTS` but **not** in the non-code exclusion list, so if graphifyy's dispatch knows them they route to the symbol chunker.

Text chunking: paragraph splitter, 2000 chars target, 200 overlap (`chunk_text`, `chunking.py:41-79`).

### 7.2 What is actually configured to be ingested (fact)

`opencg.yaml:74-76`: `ingestion.git.repos: []` — "populated at runtime via the ingestion CLI or admin UI". **The shipped configuration ingests nothing.** No default corpus, no sample dataset.

The only repository named anywhere is a docs example: `make ingest-git REPO=https://github.com/anthropics/anthropic-cookbook` (`Makefile:59-60`, `README.md:64`). That repo is predominantly Jupyter notebooks and Markdown. `.ipynb` is in neither `TEXT_EXTS` nor obviously in `gex._DISPATCH` — **could not verify whether the one repository the README tells users to ingest would produce code chunks at all.** Materially affects any claim about first-run code/prose ratio.

### 7.3 The only fixture (fact)

`tests/smoke/fixtures/knowledge-repo/`, mounted read-only (`docker-compose.yml:161-162`). **Two files.**

`README.md` — 11 lines of prose:

```5:7:tests/smoke/fixtures/knowledge-repo/README.md
The amber-context protocol improves context windows by selecting concise private knowledge
before an AI tool answers. The openCG catalogue is related to context windows because
retrieval supplies only the evidence needed for the current task.
```

`context_tools.py` — 12 lines, two top-level functions, one calling the other.

In `cloud` mode `context_tools.py` is deleted before the ingest (`run.sh:168-170`) — the cloud canary is prose-only, bounded to 1 document and 2 chunks (`:196-197`). Stub mode is bounded to 10 documents and 20 chunks (`:188-189`).

The chat stub returns a fixed two-concept, one-`related_to` payload at `confidence: 0.99` (`tests/smoke/chat_stub/server.py:15-44`).

### 7.4 What the smoke test asserts about the graph (fact)

- Code graph: `concepts ≥ 2`, `graphifyy/%` edges `≥ 1`, chunks with `metadata ? 'symbol_id'` `≥ 1` (`run.sh:319-338`).
- Vocabulary: asserts **seven** names — `depends_on defined_in supersedes mentions related_to causes derived_from` (`:342`) — message says "seven seeded relationship names present" (`:350`). `calls`, `imports`, `uses` are **not** asserted, though the spec requires ten (§8.4).
- A `text-extractor/%` candidate edge appears, traversal returns ≥ 1 edge, promotion returns `confirmed`, an audit row exists (`:352-395`).
- **Nothing asserts anything about `symbol_kind`** on either chunk or concept.

### 7.5 Honest assessment of the code-versus-prose ratio

**Cannot be answered from the repository.** No ingested corpus, no configured repo list, no dataset.

- **Fact:** the fixture is 50/50 by file count (2 files), 100% prose in cloud mode.
- **Fact:** discovery is maximal on the code side (~80 extensions) and a fixed 13-extension list on the prose side.
- **Fact:** chunk *counts* skew toward code for code-heavy repos — one chunk per symbol vs one per ~2000 characters.
- **Fact:** only prose chunks trigger a model call (`pipeline_runner.py:189`), so on a code-heavy repo the LLM extractor runs rarely and the graph is overwhelmingly graphifyy-derived; on a docs repo the inverse.
- **Inference, clearly labelled:** because every symbol chunk plus every external import target becomes a `confirmed` concept (`graph_writer.py:117-208`), while prose concepts are bounded by what a 4B model volunteers per 2000-character window, a typical software repository's graph would likely be numerically dominated by code concepts. **No runtime measurement supports this; do not treat it as measured.**

---

## 8. Where code and spec disagree

### 8.1 `concept.symbol_id` / `symbol_kind` are not in the concept-table requirement

**Spec** (`openspec/specs/knowledge-graph/spec.md:252`) enumerates required `opencg.concept` columns: `concept_id, tenant, name, dedupe_key, description, aliases, state, confidence, extractor_version, created_at, updated_at, tombstoned_at`. **`symbol_id`, `symbol_kind`, `source_entity_id` are absent.**

**Code** has all three (`040_graph.sql:64-66`). The `symbol_kind` requirement that exists (`spec.md:126-133`) is scoped to **chunk metadata**, not the concept table.

The one type-bearing column on the node table is undocumented at the requirement level. Its presence in wire types and UI comes from an archived UI change assuming it (`archive/2026-06-17-update-graph-map-detail/design.md:43-45`, "Show `symbol_kind` directly (it already exists)").

### 8.2 `symbol_kind` value set: spec says four, code produces five, one of the four is unreachable

**Spec** (`spec.md:131`): "`symbol_kind` (one of `class`, `function`, `method`, `module`)". Same in two archived predecessors. The ingestion spec is narrower — three values (`openspec/specs/ingestion/spec.md:107`).

**Code**: `chunking._symbol_kind` produces `module | method | function | class` **plus `"merged"`** (`:242`) — a fifth value in no spec. And `graph_writer._kind_from_label` can return `None | method | function | class` — **never `"module"`**, so the concept table cannot hold one of the four mandated values.

### 8.3 Traversal must expose `description`; it does not

**Spec** (`spec.md:222`): "hydrate node rows from `opencg.concept` so `name`, **`description`**, and `state` are present."

**Code**: hydration selects `concept_id, tenant, name, state, confidence, aliases, symbol_id, symbol_kind, updated_at, tombstoned_at` (`graph.py:298-299`) — no `description` — and `ConceptListItem` has no `description` field (`types.py:206-216`).

### 8.4 The smoke test verifies seven of the ten required vocabulary entries

**Spec** (`spec.md:10, 24`): "ten default vocabulary entries". **Code**: the seed inserts ten (`040_graph.sql:32-43`), but verification asserts seven (`run.sh:342, 350`).

### 8.5 Deprecated vocabulary does not reject new edges

**Spec** (`spec.md:35`): "new edge inserts with `type = "causes"` are rejected with a `vocab_deprecated` error."

**Code**: the FK checks existence only (`040_graph.sql:83`) — `deprecated_at` is not part of it. `_assert_active_vocab` (`graph.py:984-995`) is invoked from exactly one call site, `patch_edge` (`:552`). Neither writer calls it. The prose path is *indirectly* protected because `load_vocabulary` filters `WHERE deprecated_at IS NULL` (`text_graph_writer.py:247`) — but the code path's `_RELATION_MAP` is a **compile-time constant** (`graph_writer.py:44-51`), so deprecating `calls` would not stop a single `calls` edge from being written.

### 8.6 The spec attributes writes to `extract_for_chunk`, which writes nothing

**Spec** (`openspec/specs/retrieval-pipeline/spec.md:167-173`) requires `extract_for_chunk` to "Upsert concepts and edges … in a single transaction" and emit the `pipeline.graph_extract` span.

**Code**: `extract_for_chunk` (`extract.py:184-277`) takes no database handle and performs no writes; persistence lives in `write_text_graph`, called separately (`pipeline_runner.py:201-207`). The span is named `pipeline.graph_extract_text` (`extract.py:204`) — which is what the *same spec file* requires 156 lines earlier (`spec.md:11`). **The spec contradicts itself at `:11` versus `:173`.**

### 8.7 The extraction-disable requirement describes behaviour the function does not have

**Spec** (`retrieval-pipeline/spec.md:183-186`): "WHEN `providers.chat.extraction.enabled = false` THEN `extract_for_chunk` is a no-op…"

**Code**: `extract_for_chunk` has no `enabled` check (`extract.py:184-277`). The gate is entirely in callers (`pipeline_runner.py:76`, `reextract.py:50-51`). Behaviourally correct, literally unmet. The config path is also `providers.extraction.enabled`, not `providers.chat.extraction.enabled` (`config.py:64-67`).

### 8.8 The depth cap returns 422, not 400

**Spec** (`knowledge-graph/spec.md:236-239`): "rejected with `400 Bad Request`". **Code**: `depth: int = Query(default=2, ge=1, le=4)` (`routes.py:124`) — FastAPI parameter-validation failure is `422`. Same mismatch for vector-search `top_k` (`retrieval-pipeline/spec.md:75-78` vs `admin_routes.py:38`).

### 8.9 A near-miss worth recording

**Spec** (`knowledge-graph/spec.md:164`): "Ingestion SHALL run a *concept-and-relationship extractor* on **every chunk**".

**Code**: only non-code chunks (`pipeline_runner.py:189`). Reconciled in spirit by the separate "Code extraction MUST NOT call any chat model" requirement (`spec.md:41`) — the baseline is internally consistent once both are read together, but "every chunk" is literally false. The same spec refers to "an `evidence_uri TEXT`" (`spec.md:168`), a column that does not exist — the schema uses `relationship_evidence.entity_id UUID` with a real FK (`040_graph.sql:108`).

---

## 9. What the graph cannot answer today

**1. "Show me only the functions in this neighbourhood."**
`GET /graph/traverse` accepts `types`, `depth`, `limit`, `include_candidates` and nothing else (`routes.py:119-127`). No node-side predicate in the route, store method (`graph.py:230-239`), Cypher (`:282-286`), hydration query (`:296-307`), or `TraverseRequest` (`types.py:252-257`). `symbol_kind` is *returned* per node (`:299`) but cannot be *filtered on* server-side.

**2. "How many functions versus classes versus topics are in the graph?"**
No aggregate endpoint (`routes.py:55-321`). Client-side would be unreliable: prose concepts and external imports have `symbol_kind = NULL`, every file node is mislabelled `"class"`. `list_concepts` caps at 200 rows with no kind filter.

**3. "What calls `select_context`?" — as distinct from "what does `select_context` call?"**
The AGE pattern is undirected (`graph.py:283`) and `_reachable_ids` inserts both directions (`:961-962`). Direction survives per edge (`:315-316`), so a client could post-filter — but only after receiving the full undirected neighbourhood, and `limit` is applied *before* the client sees it (`:976-977`), so a high-in-degree node exhausts the budget on callers when you asked about callees.

**4. "Is this `defined_in` edge sensible?"**
No notion of what may sit on either end. The FK constrains `type` (`040_graph.sql:83`); endpoint FKs constrain only existence (`:84-85`). `filter_result` checks vocabulary membership and confidence and nothing else. So `(Prompt Caching) -[calls]-> (Context Windows)` inserts cleanly and appears in traversal once promoted.

**5. "Which candidate edges are structurally implausible, so I can reject them in bulk?"**
Every review action is single-target (`routes.py:238-256`). No bulk endpoint, and no query dimension a bulk selector could use beyond `state` and `type` (`graph.py:186-203`).

**6. "Find the concept named `os` that is a Python module, not the one from prose about operating systems."**
Both collide on `dedupe_key = "os"` and merge into one row (`040_graph.sql:72`). The dedupe key derives from the surface name alone with no kind component. `test_uses_authoritative_concept_ids_after_dedupe_conflict` demonstrates the prose writer adopting a pre-existing code concept's id on exactly this path — **a designed behaviour, not an edge case.**

**7. "Show me every concept extracted from code, versus from prose."**
The only signal is the `extractor_version` free-text string. Not indexed (`040_graph.sql:72-74`), not a filter on `list_concepts` or `list_edges`, and not returned by `list_concepts` at all (`:80-81`). The `re-extract` path makes it worse: because it feeds code chunks to the LLM (§2.5), a `text-extractor/…` version can legitimately attach to evidence for a code chunk.

**8. "Which functions in this module have no test coverage / no documentation / no owner?"**
Requires both a node-side kind predicate (absent) and negative-existence traversal (absent — traversal returns only reachable subgraphs, `graph.py:339-347`).

**9. "Roll up this neighbourhood — collapse the 40 methods into their 6 classes."**
No hierarchy. `defined_in` carries containment but nothing marks it as a containment relation — `directed` and `inverse` are stored and never read (§1.1). And `contains` and `method` both map onto `defined_in` (`graph_writer.py:48-49`), so class-membership and file-membership are indistinguishable after the write.

**10. "Use the graph to improve this retrieval."**
`/retrieve` never touches `GraphStore` (§5), `RetrievalRequest.filters` is discarded, the Qdrant payload has no kind key, and **there is no endpoint mapping an `entity_id` (what retrieval returns) to a `concept_id` (what traversal needs)**. The reverse exists only as `evidence_entity_ids` on concept detail (`graph.py:128-129`, `:181`).

**11. "When did this concept's kind change, and who changed it?"**
`patch_concept`'s allow-list is `{name, description, aliases}` (`:414`), so `symbol_kind` cannot be changed through the API at all. `ON CONFLICT` `COALESCE`s it (`graph_writer.py:140`), so the first value is permanent. `graph_audit_log.before`/`after` capture the whole row as JSONB (`:1025-1026`) so a kind *would* be auditable if anything could change it — but `target_kind`'s `CHECK` is closed (`050_graph_audit.sql:16`).

**12. "Which relation types are actually being used, and on what?"**
`opencg_extractor_edges_total{relation,state}` exists (`metrics.py:49-54`) but is incremented only from the prose extractor (`extract.py:261-265`), with `state` hardcoded `"candidate"` — so it cannot report the code path at all, nor post-review state. No metric or endpoint reports edge counts by type from the database.

---

## 10. Where a type would plug in

No opinion on whether it should.

### Schema
- `infra/postgres/init/040_graph.sql:49-70` — `opencg.concept` body; `:72-74` — index set.
- `040_graph.sql:20-43` — `relationship_vocab` columns and ten-row seed, if relation types carried domain/range.
- `050_graph_audit.sql:16` — `target_kind CHECK`, a closed set.
- `050_graph_audit.sql:62-90` — AGE label bootstrap, which today creates one vertex label `Concept` (`:71-74`).
- `020_catalog.sql:27-32` — `opencg.entity` index set, if `metadata->>'symbol_kind'` needed to be queryable.
- `040_graph.sql:122-126` and `050_graph_audit.sql:93-94` — `GRANT` blocks, for any new table.

### Code-path writes
- `graph_writer.py:80-85` — `_kind_from_label`.
- `:100-104` — node filter, which today admits the module node.
- `:126` — the `kind = _kind_from_label(label)` call site.
- `:127-155` — concept `INSERT` (columns `:129-133`, conflict `:138-142`, args `:144-154`).
- `:181-198` — on-the-fly external-target `INSERT`, which writes no `symbol_*`.
- `:44-51` — `_RELATION_MAP`.
- `:216-238` — edge `INSERT`, if edges recorded a domain/range verdict.

### Prose-path writes
- `text_graph_writer.py:72-102` — declared-concept `INSERT`.
- `:188-232` — `_ensure_concept`.
- `:140-160` — edge `INSERT`.
- `:238-249` — `load_vocabulary`, which supplies the prompt's relation list.

### Extraction
- `extract.py:89-111` — `build_prompt`: `vocab_str` (`:96`) and the system-message literal (`:97-107`).
- `extract.py:41-71` — `_RESPONSE_SCHEMA` (not transmitted today).
- `providers.py:152-184` — `OllamaChat.chat`, specifically `:168-169` where `response_schema` collapses to `format: json`.
- `extract.py:149-181` — `filter_result`, the only validation gate on model output.
- `extract.py:74-86` — `ExtractionTelemetry`; `:120-146` — `parse_response`.

### Chunking
- `chunking.py:126-139` — `_symbol_kind`.
- `:239-249`, `:270-278`, `:298-306` — the three metadata dicts.
- `:180-185` — module-node exclusion, if it needed to match the graph writer.

### Runner and payload
- `pipeline_runner.py:284-317` — `_extract_code`, the only place chunks and graphify result are simultaneously in scope.
- `:218-225` — `write_code_graph` call site.
- `:163-175` — Qdrant payload construction.
- `:189-214` — prose-extraction call site.
- `reextract.py:109-146` — `_list_chunks`, if re-extract needed to stop feeding code chunks to the LLM.

### Reads, traversal, admin
- `storage/graph.py:56-95` — `list_concepts` (clauses `:66-76`, SELECT `:80-81`).
- `:97-184` — `get_concept` (main `:103-106`, neighbours `:117-129`, projection `:169-180`).
- `:230-347` — `traverse` (signature `:230-239`, type validation `:253-266`, Cypher `:276-292`, hydration `:296-307`, edge fetch `:313-330`).
- `:947-981` — `_reachable_ids`.
- `:405-464` — `patch_concept` (allow-list `:414`, UPDATE `:430-436`).
- `:731-925` — `merge_concepts`.
- `:597-647` / `:649-691` / `:693-729` — vocabulary create/patch/deprecate.
- `:984-995` — `_assert_active_vocab`.
- `graph/age.py:17-48` — `reflect_concept`, whose `MERGE (concept:Concept {…}) SET concept.tenant, .name, .state` (`:38-42`) is where an AGE-side kind would land; `:51-91` — `reflect_edge`; `:14` — `_LABEL_RE`.
- `graph/routes.py:18-22` — `ConceptPatch`; `:32-42` — `VocabCreate`/`VocabPatch`; `:60-85` — `list_concepts` route; `:119-144` — `traverse` route.

### Wire types (must move together)
- `packages/shared-py/src/opencg_shared/types.py:206-216`, `:219-224`, `:252-257`, `:265-283`, `:198-203`.
- `packages/shared/src/index.ts:184-190`, `:192-203`, `:205-211`, `:238-244`, `:251-259`.

### MCP
- `services/mcp-server/src/tools.ts:66-82` — `traverse_graph` input schema; `:139-162` — `traverseGraph`.

### Admin UI
- `app/graph/graph-model.ts:3-9` (`GraphNode`), `:32-55` (`buildGraphModel`), `:68-97` (`labelVisibility`).
- `app/graph/GraphExplorer.tsx:17-24` (`COLORS`), `:157-187` (`drawNode`), `:227-251` (controls).
- `components/ConceptRow.tsx:5-30`; `components/ConceptDetail.tsx:73-76`.
- `app/graph/page.tsx:14-19` — tab list.
- Per `AGENTS.md`, every component in `src/components/` requires a `*.stories.tsx` neighbour. Files hardcoding `symbol_kind` fixtures: `ConceptDetail.test.tsx:16`, `ConceptDetail.stories.tsx:35`, `graph-model.test.ts:14`, `test_graph_routes.py:21-22`.

### Observability, config, verification
- `packages/shared-py/src/opencg_shared/metrics.py:49-60` — `EXTRACTOR_EDGES`, `EXTRACTOR_ERRORS`.
- `config.py:55-61` — `ExtractionCfg`; `opencg.yaml:54-58` — its values.
- `tests/smoke/run.sh:319-338`, `:340-350`, `:352-379`.
- `tests/smoke/chat_stub/server.py:15-44` — `build_content`.
- `tests/smoke/fixtures/knowledge-repo/` — the two-file fixture.

---

## 11. Could not verify

The `graphifyy` package is not installed in this working tree (no entry under `.venv/lib/python3.12/site-packages/` or the uv cache), so R0 could not inspect its node schema, its `_DISPATCH` extension table, or whether it exposes first-class symbol-kind hints. Everything about graphifyy's output shape is derived from openCG's own code and test fixtures. **§3.1 flags this as an open question for the council to close against the installed package.**
