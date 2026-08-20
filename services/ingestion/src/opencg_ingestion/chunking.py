"""Chunkers — text + code.

Text chunker stays the deterministic paragraph splitter from the thin MVP.
Code chunker (`chunk_code_by_symbols`) wraps graphifyy's `extract([path])`
to produce one chunk per AST symbol (class / function / method). Chunk
metadata carries the symbol id so downstream graph writers can link evidence
back without re-parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import graphify.extract as gex

from opencg_ingestion.graphifyy_version import graphifyy_extractor_version

log = logging.getLogger(__name__)

DEFAULT_TARGET_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200
DEFAULT_MIN_SYMBOL_CHARS = 50
DEFAULT_MAX_SYMBOL_CHARS = 8000


@dataclass
class Chunk:
    index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text chunker — unchanged behaviour from the thin MVP. Kept here so callers
# import a single module.
# ---------------------------------------------------------------------------


def chunk_text(
    text: str, *, target_chars: int = DEFAULT_TARGET_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS
) -> list[Chunk]:
    """Split text into ~target_chars windows with `overlap_chars` overlap.

    Splits on paragraph boundaries (blank lines) when possible to avoid
    breaking sentences mid-thought; falls back to hard slicing.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [Chunk(index=0, text=text)]

    def hard_slice(s: str) -> list[str]:
        step = max(1, target_chars - overlap_chars)
        return [s[i : i + target_chars] for i in range(0, len(s), step)]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(p) > target_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(hard_slice(p))
            continue
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= target_chars:
            buf = f"{buf}\n\n{p}"
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)

    return [Chunk(index=i, text=c) for i, c in enumerate(chunks)]


# ---------------------------------------------------------------------------
# Code symbol chunker — Phase 4 of `adopt-graphifyy`.
# ---------------------------------------------------------------------------


# Why the chunker produced what it produced. Only `symbols` and `no_symbols`
# represent complete work; a consumer deciding whether a file can be certified
# finished must treat `partial` and `extract_failed` as unfinished. The three
# non-`symbols` values were previously indistinguishable — `no_symbols` and
# `extract_failed` share a return shape, and `partial` was reported as
# `symbols`, which would have let silent symbol loss be certified complete.
ChunkOutcome = Literal["symbols", "partial", "no_symbols", "extract_failed"]


# graphify's dispatch covers code AND a handful of prose-ish formats
# (markdown, yaml, json) where its "extraction" surfaces things like heading
# structure and link graphs. Symbol chunking is the wrong shape for those —
# they should flow through the paragraph chunker so embeddings see meaningful
# text spans. Exclude them explicitly.
_NON_CODE_EXTS_IN_DISPATCH = {
    ".md", ".markdown", ".rst", ".txt",
    ".yaml", ".yml", ".toml", ".json", ".ini",
    ".html", ".htm",
}


def is_code_path(path: Path) -> bool:
    """Whether to route this file through the symbol chunker.

    True iff graphifyy's tree-sitter dispatch knows the extension AND the
    extension represents source code (i.e., NOT markdown / YAML / JSON / HTML
    where symbol chunking would be the wrong shape).
    """
    ext = path.suffix
    if ext in _NON_CODE_EXTS_IN_DISPATCH:
        return False
    return ext in gex._DISPATCH


def _parse_line(loc: str | None) -> int | None:
    """Parse a graphifyy `source_location` like "L42" into 42."""
    if not loc or not loc.startswith("L"):
        return None
    try:
        return int(loc[1:])
    except ValueError:
        return None


def _symbol_kind(label: str) -> str:
    """Coarse classifier from graphifyy's `label` field.

    graphifyy emits labels like "Greeter", ".__init__()", ".greet()",
    "greet_template()". A method-style label starts with "." and ends with
    "()"; a free function ends with "()" but does not start with "."; a
    class is bare. This is a heuristic — good enough for chunk metadata
    until we wire in graphifyy's own kind hints.
    """
    if not label:
        return "module"
    if label.endswith("()"):
        return "method" if label.startswith(".") else "function"
    return "class"


def _split_paragraph(text: str, target: int, overlap: int) -> list[str]:
    """Reuse the text chunker's slicing for over-sized symbol bodies."""
    chunks = chunk_text(text, target_chars=target, overlap_chars=overlap)
    return [c.text for c in chunks]


def chunk_code_by_symbols(
    path: Path,
    source_text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_symbol_chars: int = DEFAULT_MIN_SYMBOL_CHARS,
    max_symbol_chars: int = DEFAULT_MAX_SYMBOL_CHARS,
) -> tuple[list[Chunk], ChunkOutcome]:
    """Yield one chunk per AST symbol in `path` using graphifyy's extractor.

    - Symbols smaller than `min_symbol_chars` are merged with adjacent
      symbols in the same parent scope.
    - Symbols larger than `max_symbol_chars` are paragraph-split, each
      sub-chunk tagged with the parent symbol's id.
    - Files that produce zero AST symbols (e.g. a config-heavy script)
      fall back to `chunk_text(source_text)` on the whole body.

    Errors from graphifyy on a single file fall back to text chunking
    rather than failing the caller.

    Returns the chunks alongside a `ChunkOutcome` naming which of those paths
    ran. `symbols` requires that every discovered symbol reached a chunk; if
    any was dropped the outcome is `partial`, because a file that lost symbols
    is not complete even though it produced chunks.
    """
    try:
        result = gex.extract([path], parallel=False)
    except Exception as exc:  # noqa: BLE001 — best-effort per-file extraction
        log.warning("graphifyy.extract failed on %s: %s; falling back to text", path, exc)
        text_chunks = chunk_text(
            source_text, target_chars=target_chars, overlap_chars=overlap_chars
        )
        return text_chunks, "extract_failed"

    raw_nodes = [
        n
        for n in result.get("nodes", [])
        if n.get("_origin") == "ast" and n.get("file_type") == "code"
    ]
    # Drop the top-level module node — its body is the whole file, which
    # would duplicate every symbol chunk inside it.
    symbol_nodes = [n for n in raw_nodes if (n.get("label") or "") not in ("", path.stem + path.suffix)]
    # graphifyy labels the module-level node as the bare filename or the
    # module stem. Filter both shapes.
    symbol_nodes = [n for n in symbol_nodes if n.get("source_location") != "L1" or _symbol_kind(n.get("label", "")) != "module"]

    if not symbol_nodes:
        # Legitimately symbol-free — a constants module, an `__init__.py`, a
        # top-level script. An empty file lands here too and yields no chunks
        # at all, which is complete rather than degraded: there is nothing for
        # a later run to redo.
        text_chunks = chunk_text(
            source_text, target_chars=target_chars, overlap_chars=overlap_chars
        )
        return text_chunks, "no_symbols"

    lines = source_text.splitlines(keepends=True)
    n_lines = len(lines)

    # Sort by start line; compute body span as [start_line, next_start_line - 1]
    # within the same parent. Without true end-line info we use the start of
    # the next sibling as the end. For the last symbol it's end-of-file.
    enriched: list[dict[str, Any]] = []
    for n in symbol_nodes:
        start = _parse_line(n.get("source_location"))
        if start is None or start < 1:
            continue
        enriched.append({**n, "_start_line": start})
    enriched.sort(key=lambda n: n["_start_line"])

    # End-line approximation: for each node, end = (next node's start - 1)
    # or n_lines if last.
    for i, n in enumerate(enriched):
        if i + 1 < len(enriched):
            n["_end_line"] = enriched[i + 1]["_start_line"] - 1
        else:
            n["_end_line"] = n_lines

    chunks: list[Chunk] = []
    out_index = 0

    def _body_for(node: dict[str, Any]) -> str:
        start = node["_start_line"]
        end = node["_end_line"]
        s = max(1, start) - 1
        e = min(n_lines, end)
        return "".join(lines[s:e])

    # First pass: merge tiny adjacent symbols within the same parent. We
    # detect "parent" by graphifyy id shape (parent prefix); a sibling
    # shares the prefix up to the last underscore segment.
    def _parent_of(node_id: str) -> str | None:
        if "_" not in node_id:
            return None
        return node_id.rsplit("_", 1)[0]

    pending: list[dict[str, Any]] = []
    pending_text = ""
    pending_parent: str | None = None
    pending_ids: list[str] = []

    def _flush_pending() -> None:
        nonlocal out_index, pending, pending_text, pending_parent, pending_ids
        if not pending_text:
            return
        meta = {
            "symbol_ids": pending_ids,
            "symbol_id": pending_ids[0],
            "symbol_kind": "merged" if len(pending_ids) > 1 else _symbol_kind(pending[0].get("label", "")),
            "start_line": pending[0]["_start_line"],
            "end_line": pending[-1]["_end_line"],
            "extractor_version": graphifyy_extractor_version(),
        }
        if pending_parent:
            meta["parent_symbol_id"] = pending_parent
        chunks.append(Chunk(index=out_index, text=pending_text.rstrip("\n"), metadata=meta))
        out_index += 1
        pending = []
        pending_text = ""
        pending_parent = None
        pending_ids = []

    for node in enriched:
        body = _body_for(node)
        if not body.strip():
            continue
        parent = _parent_of(node["id"])
        # Big symbol: flush pending, then paragraph-split.
        if len(body) > max_symbol_chars:
            _flush_pending()
            parts = _split_paragraph(body, target_chars, overlap_chars)
            for part in parts:
                chunks.append(
                    Chunk(
                        index=out_index,
                        text=part,
                        metadata={
                            "symbol_id": node["id"],
                            "symbol_kind": _symbol_kind(node.get("label", "")),
                            "start_line": node["_start_line"],
                            "end_line": node["_end_line"],
                            "extractor_version": graphifyy_extractor_version(),
                            "split": True,
                        },
                    )
                )
                out_index += 1
            continue
        # Tiny symbol: accumulate into pending under the same parent.
        if len(body) < min_symbol_chars:
            if pending_parent is not None and pending_parent != parent:
                _flush_pending()
            if pending_text and len(pending_text) + len(body) > target_chars:
                _flush_pending()
            pending.append(node)
            pending_ids.append(node["id"])
            pending_text += body
            pending_parent = parent
            continue
        # Normal symbol: flush pending and emit on its own.
        _flush_pending()
        chunks.append(
            Chunk(
                index=out_index,
                text=body.rstrip("\n"),
                metadata={
                    "symbol_id": node["id"],
                    "symbol_kind": _symbol_kind(node.get("label", "")),
                    "start_line": node["_start_line"],
                    "end_line": node["_end_line"],
                    "extractor_version": graphifyy_extractor_version(),
                },
            )
        )
        out_index += 1

    _flush_pending()

    # Completeness is measured against the emitted chunks rather than tracked
    # through the loop, so it holds for any drop path rather than only the two
    # known ones. Identity is the symbol id, not the node: graphifyy emits the
    # same symbol more than once for TypeScript (`EntityRow()` and `EntityRow`
    # share an id and a location), and the duplicate is not a lost symbol.
    # Merging is likewise a capture — `symbol_ids` records every contributor —
    # so a file whose symbols all merge into one chunk is complete.
    discovered_ids = {n["id"] for n in symbol_nodes if n.get("id")}
    captured_ids: set[str] = set()
    for chunk in chunks:
        for symbol_id in chunk.metadata.get("symbol_ids") or [chunk.metadata.get("symbol_id")]:
            if symbol_id:
                captured_ids.add(symbol_id)

    dropped = discovered_ids - captured_ids
    if dropped:
        # A symbol reached no chunk. Its text usually survives inside a
        # neighbour's span, but its identity does not, so the file is not
        # complete and must not be certified as such. Losing every symbol
        # lands here too, with no chunks at all — the extreme of the same
        # failure, and still not `extract_failed`, which never happened.
        log.warning(
            "graphifyy discovered %d symbols in %s but %d reached no chunk: %s",
            len(discovered_ids),
            path,
            len(dropped),
            sorted(dropped),
        )
        return chunks, "partial"

    return chunks, "symbols"
