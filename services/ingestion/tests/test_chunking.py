from __future__ import annotations

import importlib.metadata
from pathlib import Path

from opencg_ingestion import chunking
from opencg_ingestion.chunking import (
    chunk_code_by_symbols,
    chunk_text,
    is_code_path,
)
from opencg_ingestion.graphifyy_version import graphifyy_extractor_version


# --- text chunker (unchanged behaviour from thin MVP) ----------------------


def test_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_returns_single_chunk():
    chunks = chunk_text("hello world", target_chars=2000)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].index == 0


def test_long_text_splits_on_paragraphs():
    para = "x" * 1500
    text = "\n\n".join([para] * 4)
    chunks = chunk_text(text, target_chars=2000, overlap_chars=100)
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_oversized_paragraph_hard_sliced():
    p = "y" * 5000
    chunks = chunk_text(p, target_chars=2000, overlap_chars=200)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 2000 for c in chunks)


# --- code symbol chunker ---------------------------------------------------


# Each body is comfortably above DEFAULT_MIN_SYMBOL_CHARS so none of the three
# is swept into the tiny-symbol merge. `alpha` sat one character below the
# threshold before, which would have turned an exact-count assertion into a
# tripwire for an unrelated reason.
PYTHON_THREE_FUNCS = """\
\"\"\"Module doc.\"\"\"


def alpha():
    a = 1
    b = 2
    c = a + b
    return c * 2


def beta(x, y):
    result = x * y
    if result > 0:
        return result
    return -result


def gamma(items):
    total = 0
    for it in items:
        total += it
    return total
"""


def test_is_code_path_recognises_python_and_ts(tmp_path):
    assert is_code_path(tmp_path / "x.py") is True
    assert is_code_path(tmp_path / "x.ts") is True
    assert is_code_path(tmp_path / "x.go") is True
    assert is_code_path(tmp_path / "README.md") is False
    assert is_code_path(tmp_path / "config.yaml") is False


def _symbol_ids(chunks) -> list[str]:
    ids: list[str] = []
    for c in chunks:
        ids.extend(i for i in (c.metadata.get("symbol_ids") or [c.metadata.get("symbol_id")]) if i)
    return ids


def test_three_top_level_functions_yield_three_chunks(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, outcome = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    assert outcome == "symbols"
    # Exactly three, not "at least" — a spurious fourth chunk means a symbol
    # was split or duplicated, which a lower bound would wave through.
    assert len(chunks) == 3
    assert _symbol_ids(chunks) == ["trio_alpha", "trio_beta", "trio_gamma"]
    assert [c.text.splitlines()[0] for c in chunks] == [
        "def alpha():",
        "def beta(x, y):",
        "def gamma(items):",
    ]


def test_zero_symbol_python_file_falls_back_to_text(tmp_path):
    body = "CONFIG = {\n    'k': 'v',\n}\nVERSION = '0.1'\n"
    p = tmp_path / "config.py"
    p.write_text(body)
    chunks, outcome = chunk_code_by_symbols(p, body)
    # Correct behaviour, not degradation — the distinction a completion
    # marker needs to avoid reprocessing every constants module forever.
    assert outcome == "no_symbols"
    assert outcome not in ("extract_failed", "partial")
    # The whole body reached one paragraph chunk, with no symbol metadata.
    assert len(chunks) == 1
    assert chunks[0].text == body.strip()
    assert chunks[0].metadata == {}


def test_oversized_function_is_paragraph_split(tmp_path):
    """One function whose body is huge gets split into multiple chunks
    each tagged with the parent symbol id."""
    body_lines = ["    x = " + ("'x' * 50") + "  # filler line " + str(i) + "\n" for i in range(800)]
    src = "def huge():\n" + "".join(body_lines) + "    return 0\n"
    p = tmp_path / "huge.py"
    p.write_text(src)
    chunks, _ = chunk_code_by_symbols(p, src, max_symbol_chars=2000, target_chars=1000)
    assert len(chunks) > 1
    # Every chunk references the parent symbol (which contains "huge").
    for c in chunks:
        sid = c.metadata.get("symbol_id", "")
        assert "huge" in sid, c.metadata


def test_chunk_indices_are_sequential(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, _ = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_extractor_version_recorded_on_chunks(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, _ = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    versions = {c.metadata.get("extractor_version") for c in chunks if c.metadata.get("symbol_id")}
    # At least one symbol chunk records the version.
    assert versions
    assert versions == {graphifyy_extractor_version()}


def test_extractor_version_is_the_installed_distribution():
    """`graphify` has no `__version__`, so the `getattr(..., "0.0.0")` this
    replaced stamped `graphifyy/0.0.0` on every row. The knowledge-graph spec
    requires the real version, and marker invalidation depends on it moving."""
    installed = importlib.metadata.version("graphifyy")
    assert graphifyy_extractor_version() == f"graphifyy/{installed}"
    assert graphifyy_extractor_version() != "graphifyy/0.0.0"


# --- extraction outcome ----------------------------------------------------


def _break_locations(monkeypatch, *, only: str | None = None) -> None:
    """Corrupt `source_location` on nodes the real extractor produced.

    Wrapping the real call rather than returning a synthetic result keeps the
    discover → filter → enrich path under test; a hand-built `nodes` list
    would prove only that the assertions match the fixture.
    """
    real_extract = chunking.gex.extract

    def corrupting(paths, **kwargs):
        result = real_extract(paths, **kwargs)
        for node in result.get("nodes", []):
            if only is None or only in (node.get("id") or ""):
                node["source_location"] = "not-a-line"
        return result

    monkeypatch.setattr(chunking.gex, "extract", corrupting)


def test_raising_extractor_reports_extract_failed(tmp_path, monkeypatch):
    def boom(paths, **kwargs):
        raise RuntimeError("tree-sitter exploded")

    monkeypatch.setattr(chunking.gex, "extract", boom)
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, outcome = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    assert outcome == "extract_failed"
    # The paragraph chunker ran over the whole body — the same shape as the
    # symbol-free path, which is why the outcome has to be reported. Assert
    # the text, not just the absence of symbol metadata.
    assert len(chunks) == 1
    assert chunks[0].text == PYTHON_THREE_FUNCS.strip()
    assert chunks[0].metadata == {}


def test_dropped_symbol_reports_partial(tmp_path, monkeypatch):
    """One of three symbols has an unparseable `source_location`. Two chunks
    come back and the file looks fine, which is exactly why `symbols` cannot
    mean "at least one": a marker here would freeze the loss permanently."""
    _break_locations(monkeypatch, only="trio_beta")
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, outcome = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)

    assert outcome == "partial"
    assert outcome != "symbols"
    assert len(chunks) == 2
    # `beta`'s identity is gone even though its text was absorbed into the
    # span of the symbol above it — the loss the outcome has to surface.
    assert _symbol_ids(chunks) == ["trio_alpha", "trio_gamma"]
    assert "def beta(x, y):" in chunks[0].text


def test_losing_every_symbol_reports_partial(tmp_path, monkeypatch):
    """The extreme of the same failure: every discovered symbol is dropped, so
    no chunks are produced at all. Still `partial` and not `extract_failed` —
    the extractor returned successfully."""
    _break_locations(monkeypatch)
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, outcome = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)

    assert chunks == []
    assert outcome == "partial"
    assert outcome != "extract_failed"


def test_empty_code_file_reports_no_symbols(tmp_path):
    """Also a zero-chunk file, but there was no work to do rather than work
    that failed, so it must NOT report `partial` — otherwise it is reprocessed
    on every run forever."""
    for name, body in (("empty.py", ""), ("blank.py", "   \n\n\t\n")):
        p = tmp_path / name
        p.write_text(body)
        chunks, outcome = chunk_code_by_symbols(p, body)
        assert chunks == [], name
        assert outcome == "no_symbols", name


def test_duplicate_nodes_for_one_symbol_are_not_a_drop(tmp_path, monkeypatch):
    """graphifyy reports many TypeScript symbols twice — `EntityRow()` and
    `EntityRow` sharing one id and one `source_location`. The earlier of the
    pair gets a zero-length span and is discarded, so accounting that counted
    raw nodes would call half of `services/admin-ui` `partial` and never let
    those files earn a marker. One symbol reported twice is one symbol.
    """
    real_extract = chunking.gex.extract

    def duplicating(paths, **kwargs):
        result = real_extract(paths, **kwargs)
        nodes = result.get("nodes", [])
        twin = next(n for n in nodes if (n.get("id") or "").endswith("_beta"))
        nodes.append({**twin, "label": (twin.get("label") or "").rstrip("()")})
        return result

    monkeypatch.setattr(chunking.gex, "extract", duplicating)
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks, outcome = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)

    assert outcome == "symbols"
    assert _symbol_ids(chunks) == ["trio_alpha", "trio_beta", "trio_gamma"]


def test_merged_tiny_symbols_are_captured_not_dropped(tmp_path):
    """Merging shares one chunk between several symbols. Every contributor is
    recorded in `symbol_ids`, so the file is complete — accounting that keyed
    on chunk count instead of symbol identity would call this `partial`."""
    body = "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 3\n"
    p = tmp_path / "tiny.py"
    p.write_text(body)
    chunks, outcome = chunk_code_by_symbols(p, body)

    assert outcome == "symbols"
    assert len(chunks) == 1
    assert chunks[0].metadata["symbol_kind"] == "merged"
    assert chunks[0].metadata["symbol_ids"] == ["tiny_a", "tiny_b", "tiny_c"]
