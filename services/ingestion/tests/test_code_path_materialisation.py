"""Code files must reach graphifyy under their real repo-relative path, not a
random temp name — otherwise node labels and symbol ids leak the tempfile stem
(e.g. ``tmpnfv6rtq0.py``) and re-ingest is non-deterministic.

These tests exercise the real graphifyy extractor (a hard dependency of the
ingestion service) on a small Python sample.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from opencg_ingestion import pipeline_runner
from opencg_ingestion.connectors.git import GitDocument

# A random-tempfile stem looks like ``tmp`` + base32-ish run of chars.
_TMP_STEM = re.compile(r"tmp[a-z0-9]{6,}")

_SAMPLE = """import os
import re


def parse_registry(text):
    return re.findall(r"\\w+", text)


def title_of(path):
    return os.path.basename(path)
"""


def _doc(rel: str) -> GitDocument:
    return GitDocument(
        entity_id="parent",
        title=rel,
        body=_SAMPLE,
        source="git",
        source_uri=f"git://repo/{rel}",
        source_revision="abc",
        content_hash="hash",
        metadata={"path": rel, "ext": ".py"},
    )


@dataclass
class _Span:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def set_attribute(self, *args, **kwargs):
        return None

    def record_exception(self, *args, **kwargs):
        return None


class _Tracer:
    def start_as_current_span(self, name: str, **_kwargs) -> _Span:
        return _Span()


# --- helper: materialisation + cleanup ------------------------------------


def test_materialised_path_uses_real_basename_and_cleans_up():
    doc = _doc("evals/checks.py")
    captured: Path | None = None
    with pipeline_runner._materialised_code_path(doc, Path("evals/checks.py")) as p:
        captured = p
        assert p.exists()
        assert p.name == "checks.py"  # real basename, not a tmp stem
        assert not _TMP_STEM.search(p.stem)
    # temp tree removed after the context exits
    assert captured is not None and not captured.exists()


def test_materialised_path_cleans_up_on_exception():
    doc = _doc("evals/checks.py")
    captured: Path | None = None
    with pytest.raises(ValueError):
        with pipeline_runner._materialised_code_path(doc, Path("evals/checks.py")) as p:
            captured = p
            assert p.exists()
            raise ValueError("boom")
    assert captured is not None and not captured.exists()


def test_materialised_path_passes_through_existing_absolute_file(tmp_path):
    real = tmp_path / "real.py"
    real.write_text(_SAMPLE, encoding="utf-8")
    doc = _doc("real.py")
    with pipeline_runner._materialised_code_path(doc, real) as p:
        assert p == real  # no copy when a genuine on-disk path exists
    assert real.exists()  # MUST NOT delete a real source file


def test_materialised_path_sanitises_traversal():
    doc = _doc("../../etc/passwd")
    with pipeline_runner._materialised_code_path(doc, Path("../../etc/passwd")) as p:
        assert p.exists()
        # the write stays inside a temp dir, never the real /etc/passwd
        assert p.resolve() != Path("/etc/passwd")
        assert "opencg-code-" in p.as_posix()


# --- _extract_code: real graphifyy naming + determinism --------------------


@pytest.mark.asyncio
async def test_extract_code_names_reflect_real_path():
    doc = _doc("evals/checks.py")
    chunks, graph = await pipeline_runner._extract_code(_Tracer(), doc, Path("evals/checks.py"))
    assert graph is not None

    labels = [str(n.get("label", "")) for n in graph.get("nodes", [])]
    ids = [str(n.get("id", "")) for n in graph.get("nodes", [])]
    symbol_ids = [c.metadata.get("symbol_id", "") for c in chunks]

    # nothing carries a random tempfile stem
    for value in [*labels, *ids, *symbol_ids]:
        assert not _TMP_STEM.search(value), f"temp stem leaked into {value!r}"

    # the real filename / symbol names survive
    assert any("checks" in v for v in [*ids, *symbol_ids])
    assert any(s for s in symbol_ids), "expected at least one symbol chunk"


@pytest.mark.asyncio
async def test_extract_code_symbol_ids_are_stable():
    doc = _doc("evals/checks.py")
    chunks_a, _ = await pipeline_runner._extract_code(_Tracer(), doc, Path("evals/checks.py"))
    chunks_b, _ = await pipeline_runner._extract_code(_Tracer(), doc, Path("evals/checks.py"))

    ids_a = [c.metadata.get("symbol_id") for c in chunks_a]
    ids_b = [c.metadata.get("symbol_id") for c in chunks_b]
    assert ids_a == ids_b
    assert all(i is not None for i in ids_a)
