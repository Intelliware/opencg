---
id: ingestion
title: Ingestion
capabilities: ingestion
status: partial
services: ingestion
stores: postgres, qdrant
tagline: The front door. Turns a git repo into searchable pieces.
---

## What it is

The front door of the whole system. You hand it a git repository URL and it walks
every file, decides what is worth indexing, and feeds each file into the rest of
the pipeline.

Nothing else in openCG does anything useful until content has come through here.

## Why it exists

A retrieval system is only as good as what it has read. Ingestion is the part
that does the reading, and it is deliberately conservative: it would rather skip
a file it cannot handle cleanly than store garbage that pollutes search results
forever.

## Flow

### 1. Trigger a run
Either the CLI (`opencg-ingest git <repo_url>`) or the HTTP API
(`POST /run/git` on port 8100). The HTTP route queues the work with FastAPI
`BackgroundTasks` and returns immediately with `status: "queued"`, so the admin
UI does not block on a long clone.
file: services/ingestion/src/opencg_ingestion/cli.py, services/ingestion/src/opencg_ingestion/server.py

### 2. Shallow-clone the repository
`git clone --depth 1` into a temporary directory, then `git rev-parse HEAD` to
record the exact commit. That SHA is stored on every row the run produces, so
you can always answer "which version of the repo did this text come from".
file: services/ingestion/src/opencg_ingestion/connectors/git.py

### 3. Discover the files worth indexing
Two discovery passes are merged. **graphifyy** identifies real source code across
roughly 80 extensions and 28 tree-sitter languages. A manual extension list
catches prose and config: `.md`, `.markdown`, `.rst`, `.txt`, `.yaml`, `.yml`,
`.toml`, `.json`, `.ini`, `.html`, `.css`, `.scss`, `.sass`. If a path appears in
both passes, the code path wins.
file: services/ingestion/src/opencg_ingestion/connectors/git.py

### 4. Filter out what cannot be handled
Anything larger than **1 MB** is skipped. Anything that is not valid UTF-8 is
skipped. Binaries and unrecognised extensions never enter the list at all, and
graphifyy honours the repo's own `.graphifyignore` plus the usual noise
directories like `node_modules`.
file: services/ingestion/src/opencg_ingestion/connectors/git.py

### 5. Build a stable document identity
Each surviving file becomes a document with a SHA-256 hash of its raw bytes and
a **deterministic** UUID derived from `{tenant}:{source_uri}`. Because the ID is
derived rather than random, re-ingesting the same file always lands on the same
row instead of creating a duplicate.
file: services/ingestion/src/opencg_ingestion/connectors/git.py

### 6. Hand off to the per-document pipeline
For each document: write a parent row to the catalog, chunk the content, write a
row per chunk, embed each chunk, upsert the vector, and run graph extraction.
Those steps are covered by the Chunking, Model Providers, Vector Index, Catalog
Store, and Knowledge Graph pillars.
file: services/ingestion/src/opencg_ingestion/pipeline_runner.py

### 7. Record the run
Counts of documents and chunks land in an in-memory ring buffer of the last 100
runs, which is what `/ingestion` in the admin UI displays.
file: services/ingestion/src/opencg_ingestion/runs.py

## Facts
- Only working connector: **git**
- Service port: **8100**
- Max file size: **1 MB**
- Skips: non-UTF-8, binaries, unknown extensions, `.graphifyignore` matches
- Readiness depends on Postgres, Qdrant, and Ollama all answering
- `opencg-ingest re-extract` re-runs graph extraction on existing chunks without re-embedding

## Gaps
- **No PDFs, images, OCR, or file upload.** The Confluence, web-indexer, and custom-API connectors are declared in `GET /connectors` but report themselves as deferred.
- **No unchanged-content short-circuit.** `content_hash` is stored but never compared before work begins, so re-ingesting a repo re-chunks and re-embeds every file even if nothing changed.
- **Deleted files are never tombstoned.** A file removed from the repo upstream stays in the catalog and in Qdrant indefinitely.
- **Run history is in-memory only.** Restarting the container loses it; there is no persistent job queue, no retry, and no scheduler.
