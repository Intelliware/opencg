---
id: knowledge-graph
title: Knowledge Graph
capabilities: knowledge-graph, background-enrichment
status: partial
services: pipeline, ingestion, postgres
stores: postgres
tagline: Concepts and named relationships between them, extracted automatically and reviewed by a human.
---

## What it is

The part that goes beyond "documents matching your words". Instead of storing
documents, it stores **ideas** and **named connections between ideas**.

"Prompt Caching" `depends_on` "Anthropic API". Function `parse_config` `calls`
function `load_yaml`. Module `server` `imports` module `router`.

Four tables do the work: `concept` holds the nodes, `relationship_edge` holds
typed arrows, `relationship_evidence` records which source chunk justified each
arrow, and `relationship_vocab` constrains which arrow types are even legal.

## Why it exists

Search answers "what mentions this". A graph answers "what is connected to this,
and how" — which is the question people actually ask when they are trying to
understand a system rather than look up a fact.

The design's central safety idea is the **candidate / confirmed split**. Code
parsing is deterministic and lands as `confirmed`. An LLM's guesses land as
`candidate` and stay quarantined out of traversal results until a human promotes
them. That is what makes automatic extraction safe to run at all.

## Flow

### 1. Constrain the vocabulary first
Only ten relationship names are legal, seeded at database init: `depends_on`,
`defined_in`, `supersedes`, `mentions`, `related_to`, `causes`, `derived_from`,
`calls`, `imports`, `uses`. A foreign key on the edge table means an unknown
type is rejected by the database, not just by application code.
file: infra/postgres/init/040_graph.sql

### 2. Code path: parse, do not guess
For source files, graphifyy walks the syntax tree and reads off exactly which
function calls which and which module imports what. No model, no tokens, no
hallucination. These edges land as `state = 'confirmed'` with `confidence = 1.0`,
because parsing is not an opinion.
file: services/ingestion/src/opencg_ingestion/graph_writer.py

### 3. Prose path: ask a model for JSON
For text chunks, the chunk is sent to `gemma3:4b` with a prompt that names the
ten legal relations and asks for `{concepts, relations}` JSON with a confidence
per relation. Concept names are requested as short noun phrases; the model is
told to be conservative and emit only what the text clearly supports. Input is
truncated at 8,000 characters.
file: services/pipeline/src/opencg_pipeline/graph/extract.py

### 4. Distrust the model's output
The response is parsed defensively — code fences stripped, the first `{...}` span
extracted, schema-validated. Then anything using a relation outside the
vocabulary is dropped, and anything below **0.6 confidence** is dropped. What
survives is written as `state = 'candidate'`.
file: services/pipeline/src/opencg_pipeline/graph/extract.py

### 5. Never fail the ingest
Extraction is best-effort by rule. A timeout, a parse failure, or an unavailable
model increments `opencg_extractor_errors_total{reason}`, logs a warning naming
the chunk, and lets ingestion continue. One bad chunk cannot break a run.
file: services/ingestion/src/opencg_ingestion/pipeline_runner.py

### 6. Deduplicate concepts on a normalised key
Concept names are folded to a `dedupe_key` — Unicode NFKC normalised, lowercased,
whitespace collapsed — with a unique index on `(tenant, dedupe_key)`. "Prompt
Caching", "prompt caching", and "Prompt  Caching" all become one node.
file: services/pipeline/src/opencg_pipeline/graph/extract.py

### 7. Mirror into Apache AGE for traversal
The Postgres tables stay authoritative, but every concept and edge is also
`MERGE`d into an Apache AGE graph as `Concept` vertices and one edge label per
vocabulary entry. This mirror exists purely so multi-hop questions can be asked
in openCypher instead of recursive SQL.
file: services/pipeline/src/opencg_pipeline/graph/age.py

### 8. Traverse on request
`GET /graph/traverse` runs a Cypher variable-length match from a start concept,
hydrates node metadata back from Postgres, filters edges by state and type, then
trims breadth-first to the requested depth and limit. Candidates are excluded
unless explicitly requested.
file: services/pipeline/src/opencg_pipeline/storage/graph.py

### 9. Review in the admin UI
The `/graph` page lets a human promote, demote, edit, merge, or tombstone
concepts and edges. Every transition writes an append-only row to
`graph_audit_log` with before and after snapshots.
file: services/pipeline/src/opencg_pipeline/graph/routes.py

## Facts
- Tables: `concept`, `relationship_edge`, `relationship_evidence`, `relationship_vocab`, `graph_audit_log`
- **10** seeded relationship types; unknown types rejected by foreign key
- Code extraction: **graphifyy**, deterministic, `confirmed`, confidence 1.0
- Prose extraction: **`gemma3:4b`** via Ollama Cloud, `candidate`, confidence floor **0.6**
- Traversal: depth default **2**, max **4**; limit default **50**, max **200**
- AGE vertex label `Concept`; one edge label per vocabulary entry
- `opencg-ingest re-extract` re-runs extraction on existing chunks, skipping ones already at the current extractor version

## Gaps
- **The graph is not consulted during retrieval.** `/retrieve` is pure hybrid text search. Traversal is a separate, deliberate call, so the graph does not yet improve normal search results. This was deferred on purpose so its impact could be measured in isolation.
- **No concept clustering or graph analytics.** No centrality, no communities, no "most important concept" ranking.
- **No background enrichment worker.** Extraction only happens inline during ingest or via the manual `re-extract` command; nothing continuously revisits stale content.
- **Candidate review is entirely manual**, with no bulk actions and no active learning from prior decisions.
