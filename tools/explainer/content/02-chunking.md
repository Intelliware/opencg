---
id: chunking
title: Chunking
capabilities: ingestion
status: shipped
services: ingestion
tagline: Cuts files into pieces small enough to search, without cutting mid-thought.
---

## What it is

The step that turns a whole file into a handful of searchable pieces. You cannot
embed a 5,000-line file as a single vector and get useful results, because the
meaning of everything averages out into mush.

openCG has **two different choppers** and picks between them based on file type.
That split is the most interesting mechanic in the ingestion path.

## Why it exists

Chunk boundaries decide search quality. A boundary in the wrong place gives you
a result that starts mid-sentence and answers nothing. For prose, "the wrong
place" means splitting an argument in half. For code, it means splitting a
function in half, which is far worse, because half a function is not just less
useful than the whole thing, it is actively misleading.

## Flow

### 1. Decide which chopper to use
`is_code_path()` asks whether the extension is one graphifyy can parse, then
subtracts an explicit exclusion list. Prose formats like `.md`, `.yaml`,
`.json`, and `.html` are forced down the text path even though graphifyy
recognises them, because symbol-splitting a YAML file is meaningless.
file: services/ingestion/src/opencg_ingestion/chunking.py

### 2. Prose path: pack paragraphs to a target size
Split the text on blank lines, then pack whole paragraphs into buckets of about
**2,000 characters** with a **200-character overlap** between neighbours. The
overlap means a sentence that straddles a boundary still appears complete in one
of the two chunks. A single paragraph bigger than the target is hard-sliced with
a stride of 1,800 characters.
file: services/ingestion/src/opencg_ingestion/chunking.py

### 3. Code path: one chunk per symbol
Instead of splitting by size, parse the file into a syntax tree with graphifyy
and emit **one chunk per function, method, or class**. A search hit then points
at a whole coherent unit rather than an arbitrary window. Each chunk carries its
symbol id, symbol kind, start and end lines, and parent scope as metadata.
file: services/ingestion/src/opencg_ingestion/chunking.py

### 4. Fix up symbols that are too small or too large
Symbols under **50 characters** get merged with adjacent symbols in the same
parent scope, so a file of one-line getters does not become fifty near-useless
chunks. Symbols over **8,000 characters** get paragraph-split, and the resulting
pieces are tagged `split: true`.
file: services/ingestion/src/opencg_ingestion/chunking.py

### 5. Fall back safely
If graphifyy finds no symbols at all, or throws, the file quietly falls back to
the prose chopper. A parser failure degrades chunk quality; it never drops the
file.
file: services/ingestion/src/opencg_ingestion/chunking.py

### 6. Mint deterministic chunk ids
Text chunks get `uuid5(namespace, "{parent_id}:{chunk_index}")`; symbol chunks
get `uuid5(namespace, "{parent_id}:{symbol_id}")`. Fragment URIs read
`{source_uri}#chunk=3` or `{source_uri}#symbol=<id>`, so a result can always be
traced back to a precise location.
file: services/ingestion/src/opencg_ingestion/pipeline_runner.py

## Facts
- Prose target: **2,000 characters**, overlap **200**
- Oversized-paragraph stride: **1,800 characters**
- Minimum symbol before merging: **50 characters**
- Maximum symbol before splitting: **8,000 characters**
- Code chunk metadata: `symbol_id`, `symbol_kind`, `start_line`, `end_line`, `parent_symbol_id`, `extractor_version`
- Prose chunk metadata: `path`, `ext`, `size`, `chunk_index`

## Gaps
- **graphifyy runs twice per code file** — once for graph extraction and again inside the symbol chunker. Correct, but wasteful on large repositories.
- **No semantic chunking for prose.** Boundaries are paragraph and character based; there is no model deciding where a topic actually ends.
- **Markdown structure is ignored.** Headings do not influence boundaries, so a chunk can span two unrelated sections of a long document.
