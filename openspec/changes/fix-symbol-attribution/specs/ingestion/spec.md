## MODIFIED Requirements

### Requirement: Symbol-level code chunking

The ingestion service SHALL provide `chunk_code_by_symbols(path, source_text)`, returning its chunks together with the extraction outcome defined by the *Chunker reports its extraction outcome* requirement. The function MUST:

1. Call `graphify.extract([path])` to obtain the file's symbol nodes.
2. Discard AST nodes the extractor did not attribute to **the file just parsed**, before spans are computed and before completeness is judged. A node MUST be kept when its `source_file` identifies the path passed to `graphify.extract`, and discarded otherwise. Two shapes are discarded by this test: a referenced type, whose `source_file` is empty because under single-file extraction its defining file is genuinely unknown; and an import target, whose `source_file` names a different file the extractor never read.

   The comparison MUST accept `source_file` in either an absolute or a relative form, anchoring a relative value to the **parsed file's parent directory** before comparing. graphifyy returns an absolute path on macOS and a bare basename on Linux, so a comparison written against only one form drops every node on the other platform.

   The test MUST compare the attributed path, not the presence of fields. A node attributed to this file is one of its definitions however malformed its other fields are — in particular, a node whose `source_location` is missing or unparseable MUST remain in the discovered population, so that failing to place it is reported as a loss rather than silently removing it.
3. For each surviving node, extract the source-text span between the symbol's start and end lines.
4. Yield one `Chunk` per symbol, in document order, with chunk metadata including the symbol's stable id (`module.path.ClassName.method_name` shape), the symbol kind (`class` / `function` / `method`), and the start/end line numbers.

The filter MUST NOT discard any node attributed to the file being parsed. In particular it MUST NOT be implemented by matching the node id against the module node's id: that test is unsound across languages, because for a Go file `cmd/sample.go` declaring `type Local` graphifyy derives the module id `sample` from the filename but the definition id `cmd_local` from the package directory, so a prefix test discards a genuine definition and the resulting loss is invisible.

Nor MUST it be implemented by requiring particular fields to be populated. Several supported languages return a module node with no `source_location` — Razor, cshtml, and Dart among them — so a presence test discards it and misreports symbol-free markup files. More seriously, a presence test removes a malformed definition from the discovered population, converting a reported loss into a silent one; path attribution keeps it, and it reports as `partial`.

If the extractor returns at least one code AST node for a file and none of them is attributed to the file being parsed, the attribution comparison has failed. The file MUST report `partial` rather than `no_symbols`, so it earns no completion marker, and the condition MUST be logged. This is distinct from the presence-based guard rejected above: a location-less module node is still attributed to its own file, so markup-only files do not trip it.

The filter in step 2 governs the population that completeness is measured against. A referenced type has no body in this file and correctly produces no chunk, so counting it as a discovered symbol makes every file that annotates a parameter with an imported type report itself incomplete. The filter MUST NOT change which chunks are produced or the `symbol_id` attached to them.

Edge handling:
- Symbols smaller than the configured `min_symbol_chars` (default 50) MUST be merged with adjacent symbols in the same scope, up to `target_chars` (default 2000).
- Symbols larger than the configured `max_symbol_chars` (default 8000) MUST be split by the paragraph chunker, with each sub-chunk carrying the parent symbol's id.
- Files that produce zero symbols (e.g., a config-heavy YAML script that ended up in the code path by extension) MUST fall back to the paragraph chunker for the whole file. A file whose only AST nodes besides the module node were attributed elsewhere counts as producing zero symbols.

#### Scenario: One chunk per Python function

- **WHEN** the symbol chunker processes a Python file with three top-level functions
- **THEN** three chunks are yielded, each spanning exactly one function's source range

#### Scenario: Tiny adjacent symbols merge

- **WHEN** a class has five getter methods of less than 50 characters each
- **THEN** the chunker merges them into one or two chunks that stay under `target_chars`
- **AND** the merged chunk's metadata lists all included symbol ids

#### Scenario: Oversized symbol is paragraph-split

- **WHEN** a single function body exceeds 8000 characters
- **THEN** the chunker emits multiple chunks, each tagged with the parent symbol's id
- **AND** each sub-chunk stays at or under 2000 characters

#### Scenario: File with no symbols falls back

- **WHEN** the symbol chunker is invoked on a Python file that contains only top-level statements (no defs, no classes)
- **THEN** the paragraph chunker is invoked on the whole file body
- **AND** no symbol metadata is attached to the resulting chunks

#### Scenario: A referenced type is not counted as a lost symbol

- **WHEN** the chunker processes a function whose signature annotates a parameter with an imported type, so graphifyy reports the type as an AST node alongside the function
- **THEN** the file reports the `symbols` outcome
- **AND** it does not report `partial`

#### Scenario: Filtering does not alter chunking

- **WHEN** a file containing referenced types is chunked
- **THEN** the function's chunk still spans its real body and still carries the defining symbol's `symbol_id`
- **AND** no chunk carries a referenced type's name as its `symbol_id`

#### Scenario: A definition whose id does not match the module id is kept

- **WHEN** the chunker processes a Go file `cmd/sample.go` declaring `type Local`, for which graphifyy reports module id `sample` and definition id `cmd_local`
- **THEN** a chunk is produced for `cmd_local`
- **AND** the outcome is `symbols`, because no definition was discarded

#### Scenario: A genuinely dropped symbol still reports partial

- **WHEN** a symbol defined in the file yields no chunk, for example because its `source_location` will not parse
- **THEN** the file reports `partial`
- **AND** the filter does not mask the loss

#### Scenario: A file the extractor attributes no symbols to falls back

- **WHEN** every AST node graphifyy reports for a file besides the module node is one it did not attribute to that file — either a referenced type with no `source_file`, or an import target naming another file
- **THEN** the paragraph chunker is invoked on the whole body
- **AND** the outcome is `no_symbols`, not `partial`

#### Scenario: source_file returned as a bare basename still matches

- **WHEN** the extractor returns `source_file` as a bare filename rather than an absolute path, as it does on Linux
- **THEN** the value is anchored to the parsed file's parent directory and compares equal
- **AND** the file's definitions are retained rather than all being discarded

#### Scenario: A failed attribution comparison reports partial

- **WHEN** the extractor returns code AST nodes for a file but none of them is attributed to the file being parsed
- **THEN** the outcome is `partial`, not `no_symbols`
- **AND** the condition is logged, because it means the comparison has failed rather than that the file defines nothing

#### Scenario: An import target attributed to another file is not a definition

- **WHEN** the chunker processes a Svelte file whose only statements are an import and a variable export, for which graphifyy emits an import-target node whose `source_file` names a different file it never read
- **THEN** that node is excluded from the discovered population
- **AND** the outcome is `no_symbols` rather than `partial`

#### Scenario: A markup-only file with a location-less module node still falls back

- **WHEN** the chunker processes a Razor, cshtml, or Dart file containing only markup, for which graphifyy returns a single module node attributed to that file but carrying no `source_location`
- **THEN** the node is kept, because it is attributed to the file being parsed
- **AND** the outcome is `no_symbols`, since it is the module node and yields no symbol

#### Scenario: A definition with a missing location is reported lost, not removed

- **WHEN** a node attributed to the file being parsed carries no usable `source_location`, so it yields no chunk
- **THEN** it remains in the discovered population
- **AND** the outcome is `partial`, because the loss is real and must be reported rather than filtered away
