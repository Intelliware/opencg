## Context

`chunk_code_by_symbols` calls `graphify.extract` and turns the returned AST nodes into chunks. `add-incremental-ingest` added a completeness contract on top: the function reports whether every discovered symbol produced a chunk, because a completion marker must never be granted to a file that silently lost content.

The contract works. Its input population does not. graphifyy returns nodes for symbols the file **defines** and for types the file **references**, and only the former are chunkable:

```
L84: [('graph_writer_write_code_graph', 'write_code_graph()'),
      ('catalogstore', 'CatalogStore'),
      ('any', 'Any')]
```

`CatalogStore` and `Any` come from the signature of `write_code_graph`. They are real entities in the dependency graph and carry meaningful `imports` and `uses` edges. They have no body in this file and correctly produce no chunk. The completeness check sees two discovered nodes with no matching chunk and reports the file incomplete.

Measured on this repository at the pinned graphifyy 0.8.51: 38 of 60 Python files report `partial` with nothing lost.

## Goals / Non-Goals

**Goals:**

- Judge completeness against symbols the file defines, so `partial` means real loss.
- Unblock `add-incremental-ingest`'s gate, which cannot enable while most Python files falsely report incomplete.
- Change no stored data.

**Non-Goals:**

- **Changing what graphifyy reports.** Emitting referenced types is correct and the graph depends on it.
- **Replacing the end-line approximation.** Deriving a symbol's end from the next symbol's start is imprecise — it absorbs trailing comments and blank lines. Fixing that needs real end lines from graphifyy. Out of scope; unrelated to this.
- **Backfilling anything.** Nothing stored is wrong.

## Decisions

### D1. Keep the nodes the extractor attributed to the file being parsed

**Decision.** Keep an AST node when its `source_file` identifies the file passed to `graphify.extract`. Drop the rest before completeness is judged.

**The comparison must handle two path forms, and this is not a detail.** graphifyy returns `source_file` as an absolute path on macOS and as a **bare basename on Linux** — verified inside the running ingestion container:

```
macOS:  source_file = '/var/folders/.../opencg-code-v4zx7nve/cmd/sample.go'
Linux:  source_file = 'sample.go'
```

So a relative value MUST be anchored to the parsed file's parent directory before comparing. Comparing the raw strings, or resolving a relative value against the process working directory, matches nothing in the container: every node is dropped, and the file reports having no symbols at all. Every measurement in this document was taken on macOS, where the naive comparison happens to work, which is exactly how this would have shipped.

**Rationale.** This is the question we actually need answered — *did the extractor attribute this node to the file I just handed it?* — rather than a proxy for it. Every proxy tried before it was broken by a language nobody had tested:

| Discriminator | Broken by |
|---|---|
| id begins with the module id | Go: `cmd/sample.go` declares `type Local` with id `cmd_local` from the package directory while the module id is `sample`, so a genuine definition is deleted |
| `source_file` populated | Svelte: an import target carries a `source_file` naming a file the extractor never read, survives, yields no chunk, and pins the file at `partial` forever |
| `source_file` populated and `source_location` non-empty | Razor, cshtml, Dart: the module node has no `source_location`, so it is discarded and a symbol-free markup file misreports. Worse, discarding a malformed definition removes it from the discovered population, converting a reported loss into a silent one |

Path attribution excludes both shapes that need excluding, for the right reason. A referenced type has no `source_file` because under single-file extraction its defining file genuinely is unknown. An import target names a different file. Neither was attributed here; every definition was.

**Malformed definitions self-report; misattributed ones do not.** A definition attributed to this file stays in the discovered population however broken its other fields are, so failing to place it reports as `partial` on its own — verified: emptying a real symbol's `source_location` yields `partial`, where a presence test yielded `no_symbols` and a completion marker. That property covers one of the two loss shapes. It does not cover a definition the comparison wrongly attributes elsewhere, which is removed before counting and leaves no trace. D3 carries the guard for that.

**Alternatives rejected.** *Filter by label shape* — defined functions end in `()`, but a defined class is bare and so is a referenced type. *Ask graphifyy for a node kind* — not exposed at this version.

**Scope note.** The test asks about attribution, not semantics. Some languages attribute an import statement to the importing file — `import Foundation` in Swift yields a node at `L1` attributed to the Swift file — so it is kept and chunked. That is current behaviour, unchanged by this decision, and named in the proposal's Impact as out of scope.

**How three discriminators went wrong in a row.** Each was inferred from the languages in front of me and asserted as a general property. The corpus is Python and TypeScript; graphifyy dispatches roughly 90 extensions. The lesson is not "test more languages" — a discriminator should express the actual question, so untested languages are covered by construction rather than by coincidence. The path-form discovery above is the same lesson one level down: expressing the right question does not help if the comparison implementing it is only correct on the platform you measured.

### D2. Filter before completeness, not before chunking

**Decision.** The filter changes which nodes count as *discovered*. It does not need to change which chunks are produced, and measurement confirms it does not.

**Rationale.** Verified at 0.8.51: 567 chunks before the filter, 567 after, and zero chunks change their `symbol_id`. Referenced types were already producing no chunks — they were only ever inflating the discovered count. This is why the change carries no data impact.

The filter is still applied to the node list rather than to the accounting alone, because the two must not drift apart. A future edit that starts deriving spans from a population the accounting does not share would reintroduce exactly this class of bug.

### D3. Zero symbols reports `no_symbols`; zero *attributions* reports `partial`

**Decision.** When filtering leaves no symbol nodes but at least one node was attributed to the parsed file, take the existing zero-symbol path: paragraph-chunk the whole body and report `no_symbols`. When **no** node is attributed to the parsed file at all, report `partial` and log it.

**Rationale.** The first case is a file that defines nothing — the same situation as a config-heavy script that reached the code path by extension, already specified behaviour. Its text stays searchable and `no_symbols` earns a completion marker, correctly, because there is no symbol work outstanding.

The second case means the attribution comparison itself has failed, and it is not hypothetical. graphifyy returns `source_file` as a basename on Linux and an absolute path on macOS, so a comparison that is correct on the development platform drops every node in the container. Without this guard that produces `no_symbols` and a completion marker for a file that lost all of its symbols — the worst outcome the whole change exists to prevent, arrived at through the fix for it.

**This is not the guard the previous draft carried, and the difference matters.** That one triggered on nodes failing a *field-presence* test, which was wrong in both directions: a single valid module node suppressed it while a real symbol was dropped, and it fired spuriously on Razor, cshtml and Dart, whose module nodes legitimately carry no `source_location`. Triggering on *attribution* has neither problem, because a location-less module node is still attributed to its own file. Verified across 20 languages and all 60 corpus files: it fires on nothing.

It also cannot catch everything, and the limit should be stated. If the comparison misattributes *some* definitions but not all, the survivors suppress the guard and the losses are invisible. No guard can see a node that was removed before counting. That residual is in the risks below; the guard covers the total-failure case, which is the one a platform difference actually produces.

## What an earlier draft got wrong

The first version of this proposal argued that stored data was corrupt — that a function's body was persisted under `symbol_id = "any"` and 13% of chunk ids needed rotating. That was measured against graphifyy **0.8.38**, which was pinned in `uv.lock` for local development while every container silently built against **0.8.51**, because the Dockerfiles copied `pyproject.toml` without `uv.lock` and resolved afresh at build time.

0.8.38 genuinely does mis-attribute: the referenced type wins the span collision and takes the function's body. 0.8.51 does not. So the corruption was real locally and absent from anything deployed. That divergence has since been closed by pinning the floor to 0.8.51 and making both Python images build with `uv sync --locked`.

This is recorded because the conclusion was wrong in a specific, repeatable way: the measurement environment was never verified to match the runtime environment. The corrected change is much smaller — an accounting fix with no data impact — and the difference between the two drafts is entirely down to which version was under the probe.

## Risks / Trade-offs

- **Partial misattribution is undetectable.** If the comparison wrongly rejects *some* definitions but not all, the survivors suppress D3's guard and the losses leave no trace — a node removed before counting cannot be reported. The file reports `symbols` and earns a marker while missing content. → No guard can close this; only the comparison being right closes it. Hence the dedicated regression tests, the Go case pinned as a scenario, and the requirement to exercise the Linux path form rather than only the developer's. Total misattribution, which is what a platform difference actually produces, is covered by D3.
- **`source_file` may behave differently under a multi-file extraction.** The measurement covers single-file `gex.extract([path])`, which is the only way ingestion calls it. Batching would not make references start counting as definitions — a resolved reference is attributed to its *own* file, so it is still dropped — but "the path passed to `graphify.extract`" becomes plural, so the comparison target turns ambiguous and would have to become per-node. → Named here so that any move to batched extraction revisits this decision.
- **Path forms vary by platform, and possibly by more than platform.** Absolute on macOS, bare basename on Linux, both verified. Nothing guarantees those are the only two shapes across ~90 dispatch extensions and future patch releases inside the pin. → The anchoring rule handles absolute and relative uniformly rather than special-casing the two observed forms, and D3's guard turns any unhandled shape into reprocessing rather than a false completion.
- **A sibling symlink can alias one file onto another.** If a file imports `./alias.svelte` where `alias.svelte` is a symlink to the parsed file, resolving both sides makes the import target compare equal and it is wrongly kept, yielding `partial` with no chunks. → Not reachable today: the connector materialises exactly one file into a fresh temp directory, so no sibling exists to be a symlink. Named because a future connector that materialises a subtree would make it reachable.
- **The corpus is Python and TypeScript only.** This repository contains no Go, Rust, or tracked JavaScript, and all 506 of its TypeScript AST nodes are definitions, so the TypeScript evidence shows only that nothing is wrongly dropped — it exercises no references. The Go behaviour above was established with a purpose-built fixture, not from the corpus.
- **graphifyy could change id shapes within the `<0.9` pin.** → `add-incremental-ingest`'s completion marker carries `chunker_version`, so a graphifyy change invalidates markers and forces reprocessing rather than silently absorbing the difference. 0.9.x is already excluded for an unrelated and more serious reason: it derives ids from the absolute path, so they embed the temp directory and change every run.

## Migration Plan

None required. No schema change, no stored data affected, no id rotation. Deploy the code; the next ingest reports accurate outcomes.

**Rollback** is reverting the filter, which returns the false `partial` reports. No data is written or destroyed in either direction.

## Open Questions

None. The one open question in the earlier draft — whether a file of only referenced types should report `no_symbols` or `partial` — is settled in D3.
