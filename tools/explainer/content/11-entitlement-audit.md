---
id: entitlement-audit
title: Entitlement and Audit
capabilities: entitlement-audit
status: partial
services: pipeline, postgres
stores: postgres
tagline: An append-only record of everything ever handed to a model. The database refuses to forget.
---

## What it is

Two things that belong together: the check on **who may see what**, and the
permanent record of **what was actually sent**.

The audit half is arguably openCG's real differentiator. Most retrieval systems
cannot tell you what they fed a model six months ago. This one can reconstruct
it exactly.

## Why it exists

If a private knowledge base is going to be piped into AI tools, someone will
eventually ask what leaked, when, and to whom. Answering that after the fact is
impossible unless you wrote it down at the time — so openCG writes a row on every
single retrieval, and makes that row physically impossible to alter.

## Flow

### 1. Decide what the caller may see
At assemble time each candidate's `classification` is compared against the
classifications its roles allow. `admin` and `reader` both get
`{internal, public}`; an unrecognised role gets `{public}` only. Failing closed
on unknown roles is deliberate.
file: services/pipeline/src/opencg_pipeline/stages/assemble.py

### 2. Record a verdict per candidate, not just per result
Every candidate the search surfaced gets a decision: `include` with its token
count, `deny` with `classification_restricted`, or `drop` with
`budget_exhausted`. The record shows what was considered and rejected, not only
what was returned.
file: services/pipeline/src/opencg_pipeline/stages/assemble.py

### 3. Hash the exact assembled context
SHA-256 over the ordered `(entity_id, score, text)` of the final fragments. Later
you can prove whether a given context window is the one that was served.
file: services/pipeline/src/opencg_pipeline/app.py

### 4. Write one immutable row
Who asked, what they asked, which tool, all candidate ids, all decisions, the
final ids, the hash, token counts, latency, outcome, and the model and retriever
versions in play — enough to recreate the conditions of the query.
file: services/pipeline/src/opencg_pipeline/storage/audit.py

### 5. Let the database enforce immutability
A trigger on `opencg.audit_log` **blocks DELETE entirely** and permits exactly
one kind of UPDATE: flipping `legal_hold` from false to true. This is not a
convention the application follows; it is a rule the database enforces against
every client, including a human with psql.
file: infra/postgres/init/030_audit.sql

### 6. Partition by time
The table is partitioned by `created_at` on a weekly cadence with a default
partition, so it can grow without the write path degrading.
file: infra/postgres/init/030_audit.sql

### 7. Audit the graph separately
Graph edits get their own append-only table, `graph_audit_log`, recording actor,
target kind, state transition, reason, and full before/after JSONB snapshots. It
forbids both UPDATE and DELETE.
file: infra/postgres/init/050_graph_audit.sql

### 8. Read it back
`GET /audit/recent` and `GET /audit/{id}` serve the Queries page, and a
per-entity lookup finds every audit row whose final set contained a given
entity — which is how the entity detail page shows "where this has been used".
file: services/pipeline/src/opencg_pipeline/app.py

## Facts
- Tables: **`opencg.audit_log`** (partitioned weekly) and **`opencg.graph_audit_log`**
- DELETE is blocked by trigger; the only legal UPDATE is `legal_hold` false to true
- One row per `/retrieve`, capturing every candidate and its verdict
- Role policy: `admin` and `reader` get `{internal, public}`; unknown roles get `{public}`
- Retrieval audit records `retriever_versions` and `model_versions` for recreatability

## Gaps
- **Entitlement is a hardcoded dictionary**, not policy. OPA enforcement, per-owner ACLs, and row-level rules are all deferred.
- **Admin vector search writes no audit row.** It is documented as admin-only, but it is a way to read content that leaves no trace.
- **No replay endpoint.** The audit row captures enough to recreate a query, but nothing yet consumes it to actually re-run one.
- **`vector_snapshot_id` is always null**, so a row cannot pin the exact index state it searched against.
- **No legal-hold workflow.** The column and its trigger exemption exist; no API exposes them.
