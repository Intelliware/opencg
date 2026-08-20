## Why

`add-incremental-ingest` gives `chunk_code_by_symbols` a completeness contract: report `symbols` when every discovered symbol produced a chunk, and `partial` when any were lost. A `partial` file never earns a completion marker, so it is reprocessed on the next run rather than skipped — the safety property that stops the gate freezing a half-finished file.

That accounting is counting the wrong population. graphifyy returns two kinds of AST node, and only one of them is chunkable:

- **Symbols the file defines** — `graph_writer_write_code_graph`, `graph_writer_normalize`. These become chunks.
- **Types the file references** — `catalogstore`, `any`, lifted from parameter annotations and imports. These exist so the graph can carry `imports` and `uses` edges. They are not defined here and have no body in this file, so they never become chunks and never should.

Comparing all discovered nodes against produced chunks therefore counts every referenced type as a lost symbol. Measured on this repository: **38 of 60 Python files report `partial` when nothing has been lost.**

With the gate enabled those 38 files could never be marked complete and would be re-chunked, re-embedded, and re-extracted on every run forever. That is the inverse error `add-incremental-ingest` explicitly forbids in its own goals, and it would leave the feature doing almost nothing on a Python corpus.

Nothing is wrong with graphifyy and nothing is wrong with the stored data. Reporting referenced types is correct behaviour that our completeness check misreads.

## What Changes

- **Discovery is narrowed to the nodes the extractor attributed to the file being parsed**, before completeness is judged. A node is kept when its `source_file` resolves to the path handed to `graphify.extract`, and dropped otherwise. That excludes referenced types, whose `source_file` is empty because under single-file extraction their defining file is genuinely unknown, and import targets, whose `source_file` names a different file the extractor never read.
- **A malformed definition is kept, not filtered.** A node attributed to this file stays in the discovered population however broken its other fields are, so failing to place it reports as `partial` rather than disappearing. This is why no discriminator-failure guard is needed: the failure mode reports itself.
- **A file whose only AST nodes besides the module node were attributed elsewhere** takes the existing zero-symbol path and reports `no_symbols`, so its text is still chunked and searchable.

**Not a breaking change, and not a data change.** Verified against this repository at the pinned graphifyy 0.8.51: 567 chunks before the filter and 567 after, and **zero chunks change their `symbol_id`**. The only thing that changes is the outcome each file reports — `partial` falls from 38 to 0.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ingestion`: MODIFIES *Symbol-level code chunking* to require that discovery keeps only nodes the extractor attributed to the file being parsed, to pin how a relative `source_file` is anchored, and to require `partial` rather than `no_symbols` when nothing is attributed at all.

`knowledge-graph` is deliberately **not** listed. Persisted `symbol_id` values are unchanged, so *Symbol identity flows through the catalog* still holds exactly as written. An earlier draft of this proposal claimed otherwise; see the design's "What an earlier draft got wrong" for why.

## Impact

- `services/ingestion/src/opencg_ingestion/chunking.py`: node filtering in `chunk_code_by_symbols`, ahead of the existing module-node filter.
- No schema change, no new dependency, no migration, no orphaned rows, no entity-id rotation.
- **Sequencing**: must land before `add-incremental-ingest` enables its gate (that change's task 5). It does not block that change's earlier tasks — withholding a marker from a file reporting `partial` is correct behaviour either way, and only the gate turns that into repeated work.
- **Archive ordering**: this change MUST NOT be archived before `add-incremental-ingest`. The modified requirement now references that change's *Chunker reports its extraction outcome* by name, and every outcome-asserting scenario here depends on the vocabulary it defines. Archiving first would leave the baseline citing a requirement it does not contain. This change is 27 tasks against that change's 60, so it will plausibly finish first — the constraint is on archiving, not on implementing.
- **Pre-existing and out of scope**: in some languages an import statement produces a chunk of its own — `import Foundation` in Swift yields a chunk with `symbol_id = "foundation"`. That node carries both a `source_file` and a `source_location`, so it is indistinguishable from a definition by this change's test and survives unchanged. It is current behaviour, unaffected either way, and belongs to whoever next looks at cross-language chunk quality.
- Depends on graphifyy being at or above 0.8.51, already pinned in `services/ingestion/pyproject.toml`. On 0.8.38 the same referenced types additionally stole their function's body, which is a different and worse failure; the version floor closes that and this change closes the accounting.
