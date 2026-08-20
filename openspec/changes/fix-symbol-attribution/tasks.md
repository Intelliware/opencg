## 1. Pre-flight

- [ ] 1.1 Confirm graphifyy resolves to 0.8.51 or higher in BOTH the local venv and the ingestion container. This change assumes the version floor is already in place; on 0.8.38 referenced types additionally steal their function's body, which is a different failure this change does not address.
- [ ] 1.2 Confirm `add-incremental-ingest` task 5 (the gate) is not yet implemented — this must land before it. That change's task 2 (the outcome contract) is a hard PREREQUISITE for every outcome-asserting test below and is already present in the working tree; its tasks 3 and 4 may proceed in parallel. Note also that this change must not be ARCHIVED before that one, since the modified requirement cites it by name.
- [ ] 1.3 Record the baseline so the fix can be shown to move it: count outcomes across `services/**/*.py` and `packages/**/*.py`, materialising each file into a FRESH temp directory under its repo-relative path, exactly as `_materialised_code_path` does. Expect `partial` 38, `symbols` 15, `no_symbols` 7, and 567 chunks total. An accumulating temp tree gives different numbers and is not what production does.

## 2. The filter

- [ ] 2.1 Filter AST nodes to those whose `source_file` identifies the path passed to `graphify.extract`. **Anchor a relative `source_file` to the parsed file's parent directory before comparing** — graphifyy returns an absolute path on macOS and a bare basename on Linux, so a comparison written for one form drops every node on the other. Do not resolve a relative value against the process working directory. See D1 for the three discriminators rejected before this one.
- [ ] 2.2 Do NOT filter on field presence. A node attributed to this file must be kept however malformed it is, so that failing to place it reports as `partial`. Filtering it out converts a reported loss into a silent one, which is the failure this whole change exists to prevent.
- [ ] 2.3 Apply the filter before the existing module-node filter and before the `enriched` span build, so the discovered population and the chunked population cannot drift apart.
- [ ] 2.4 Add the attribution-failure guard: if the extractor returned at least one code AST node and none is attributed to the parsed file, report `partial` rather than `no_symbols`, and log it. This is what turns a broken comparison into reprocessing instead of a false completion marker. It is NOT the presence-based guard rejected in D3 — a location-less module node is still attributed to its own file and must not trip it.
- [ ] 2.5 Confirm a file with attributed nodes but no symbol nodes still takes the existing zero-symbol path and reports `no_symbols`.

## 3. Tests

- [ ] 3.1 A function whose signature annotates a parameter with an imported type reports `symbols`, not `partial`. Use real graphifyy output rather than synthetic node dicts so the test exercises the actual node population.
- [ ] 3.2 That same file's chunk for the function still spans its real body and still carries the function's `symbol_id`, and no chunk carries a referenced type's name.
- [ ] 3.3 **Go regression**: `cmd/sample.go` declaring `type Local` and `func Build` yields chunks for both `cmd_local` and `sample_build` and reports `symbols`. `cmd_local` does not share the module id `sample`, so this test fails under the rejected prefix discriminator and is the guard against reintroducing it.
- [ ] 3.4 A file whose only AST nodes besides the module node are attributed elsewhere falls back to the paragraph chunker and reports `no_symbols`.
- [ ] 3.5 **Svelte import regression**: a Svelte file whose only statements are an import and a variable export reports `no_symbols`, not `partial`. Its import-target node carries a populated `source_file` naming another file, so this test fails under a `source_file`-populated discriminator.
- [ ] 3.6 **Markup-only regression**: a Razor or cshtml file containing only markup reports `no_symbols`. Its single module node has no `source_location`, so this test fails under a field-presence discriminator and guards against reintroducing one.
- [ ] 3.7 **The inverted risk**: empty a real definition's `source_location` entirely and assert the outcome is `partial`, not `no_symbols`. Under path attribution the node stays in the discovered population and the loss reports itself; a presence-based filter removed it and returned `no_symbols`, earning a completion marker for a file that had silently lost a symbol. This is the single most important test in the change.
- [ ] 3.8 **Linux path form**: assert a bare-basename `source_file` is anchored to the parsed file's parent and matches. This is the case that drops every node in the container while passing on macOS, so it must be tested against the basename form explicitly rather than against whatever the developer's platform emits.
- [ ] 3.9 **Attribution-failure guard**: force every node's `source_file` to name a different file and assert the outcome is `partial`, not `no_symbols`.
- [ ] 3.10 Regression: the four existing *Symbol-level code chunking* scenarios still hold — one chunk per function, tiny symbols merge, oversized symbols split, symbol-free files fall back.

## 4. Verify the corpus moves, and that nothing else does

- [ ] 4.1 Re-run the 1.3 measurement. Expect `partial` to reach 0 and `symbols` to reach 53.
- [ ] 4.2 Confirm the chunk total is still 567 and that **no chunk changes its `symbol_id`**. This is the claim that makes the change data-safe; if any id moves, stop and re-open the migration question the earlier draft raised.
- [ ] 4.3 Spot-check `graph_writer.py`: still 5 chunks, the 7,301-character chunk still under `graph_writer_write_code_graph`, outcome now `symbols`.
- [ ] 4.4 Confirm no TypeScript file regresses. Note this is weak evidence: all 506 TypeScript AST nodes in this repository are definitions, so nothing gets dropped and the check cannot show how references behave. The repository contains no Go, Rust, or tracked JavaScript, so the Go behaviour must come from the fixture in test 3.3 rather than the corpus.

## 5. Close-out

- [ ] 5.1 Run the unit suites: `uv run --package opencg-ingestion pytest services/ingestion/tests` and the pipeline equivalent. The Makefile targets are broken — they omit the `test` extra — so use the `uv run --package` form.
- [ ] 5.2 **Run the corpus measurement inside the ingestion container, not only on the host.** Every number in this change was taken on macOS, and the platform difference in `source_file` is invisible there. `docker compose -f infra/compose/docker-compose.yml exec ingestion ...` — expect the same 0 `partial` / 53 `symbols` / 7 `no_symbols`.
- [ ] 5.3 Run `bash tests/smoke/run.sh` against the live stack.
- [ ] 5.4 Check whether `tools/explainer/content/` describes symbol chunking in a way this changes; update and run `make explainer` if so.
- [ ] 5.5 Run `openspec validate fix-symbol-attribution --strict`.
