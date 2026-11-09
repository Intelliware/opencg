from __future__ import annotations

from opencg_ingestion.chunking import (
    chunk_code_by_symbols,
    chunk_text,
    is_code_path,
)

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


PYTHON_THREE_FUNCS = """\
\"\"\"Module doc.\"\"\"


def alpha():
    a = 1
    b = 2
    return a + b


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


def test_three_top_level_functions_yield_three_chunks(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    # Exactly three function symbols → three chunks (modulo merging).
    assert len(chunks) >= 3
    labels = []
    for c in chunks:
        ids = c.metadata.get("symbol_ids") or [c.metadata.get("symbol_id")]
        labels.extend(ids)
    assert any("alpha" in (i or "") for i in labels)
    assert any("beta" in (i or "") for i in labels)
    assert any("gamma" in (i or "") for i in labels)


def test_zero_symbol_python_file_falls_back_to_text(tmp_path):
    body = "CONFIG = {\n    'k': 'v',\n}\nVERSION = '0.1'\n"
    p = tmp_path / "config.py"
    p.write_text(body)
    chunks = chunk_code_by_symbols(p, body)
    assert len(chunks) >= 1
    # No symbol metadata: this is a paragraph-chunked file.
    assert all(c.metadata.get("symbol_id") is None for c in chunks)


def test_oversized_function_is_paragraph_split(tmp_path):
    """One function whose body is huge gets split into multiple chunks
    each tagged with the parent symbol id."""
    body_lines = [
        "    x = " + ("'x' * 50") + "  # filler line " + str(i) + "\n" for i in range(800)
    ]
    src = "def huge():\n" + "".join(body_lines) + "    return 0\n"
    p = tmp_path / "huge.py"
    p.write_text(src)
    chunks = chunk_code_by_symbols(p, src, max_symbol_chars=2000, target_chars=1000)
    assert len(chunks) > 1
    # Every chunk references the parent symbol (which contains "huge").
    for c in chunks:
        sid = c.metadata.get("symbol_id", "")
        assert "huge" in sid, c.metadata


def test_chunk_indices_are_sequential(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_extractor_version_recorded_on_chunks(tmp_path):
    p = tmp_path / "trio.py"
    p.write_text(PYTHON_THREE_FUNCS)
    chunks = chunk_code_by_symbols(p, PYTHON_THREE_FUNCS)
    versions = {c.metadata.get("extractor_version") for c in chunks if c.metadata.get("symbol_id")}
    # At least one symbol chunk records the version.
    assert versions
    for v in versions:
        assert v and v.startswith("graphifyy/")
