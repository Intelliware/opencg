from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest
from opencg_shared import openCGConfig
from opencg_pipeline.providers import EmbeddingResult

from opencg_ingestion import pipeline_runner
from opencg_ingestion.chunking import Chunk
from opencg_ingestion.connectors.git import GitDocument


class _Catalog:
    inserted: list[str] = []

    def __init__(self, dsn: str) -> None:
        self.inserted = []
        _Catalog.inserted = self.inserted

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def insert_entity(self, **kwargs) -> None:
        self.inserted.append(kwargs["entity_id"])


class _Vector:
    upserts: list[str] = []

    def __init__(self, **kwargs) -> None:
        self.upserts = []
        _Vector.upserts = self.upserts

    async def ensure_collection(self, source: str) -> None:
        return None

    async def upsert(self, *, entity_id: str, **kwargs) -> None:
        self.upserts.append(entity_id)

    async def close(self) -> None:
        return None


class _Embeddings:
    def __init__(self, **kwargs) -> None:
        return None

    async def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[0.1, 0.2],
            tokens_in=2,
            model="test",
            provider="ollama",
        )

    async def close(self) -> None:
        return None


class _Chat:
    model = "test-chat"

    def __init__(self, **kwargs) -> None:
        return None

    async def close(self) -> None:
        return None


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
    def start_as_current_span(self, name: str) -> _Span:
        return _Span()


@pytest.mark.asyncio
async def test_extractor_timeout_does_not_abort_chunk_loop(monkeypatch):
    calls: list[str] = []

    async def timeout_extract(**kwargs):
        calls.append(kwargs["chunk_entity_id"])
        raise asyncio.TimeoutError("slow model")

    async def vocab(*args, **kwargs):
        return ["depends_on"]

    monkeypatch.setattr(pipeline_runner, "CatalogStore", _Catalog)
    monkeypatch.setattr(pipeline_runner, "VectorIndex", _Vector)
    monkeypatch.setattr(pipeline_runner, "OllamaEmbeddings", _Embeddings)
    monkeypatch.setattr(pipeline_runner, "OllamaChat", _Chat)
    monkeypatch.setattr(pipeline_runner, "setup_otel", lambda *args: _Tracer())
    monkeypatch.setattr(pipeline_runner, "load_vocabulary", vocab)
    monkeypatch.setattr(pipeline_runner, "extract_for_chunk", timeout_extract)
    monkeypatch.setattr(pipeline_runner, "is_code_path", lambda path: False)
    monkeypatch.setattr(
        pipeline_runner,
        "chunk_text",
        lambda text: [Chunk(index=0, text="one"), Chunk(index=1, text="two")],
    )

    doc = GitDocument(
        entity_id="parent",
        title="README.md",
        body="one\n\ntwo",
        source="git",
        source_uri="git://repo/README.md",
        source_revision="abc",
        content_hash="hash",
        metadata={"path": "README.md"},
    )
    parents, chunks = await pipeline_runner.ingest_documents(
        [doc],
        cfg=openCGConfig(),
    )

    assert (parents, chunks) == (1, 2)
    assert len(calls) == 2
    assert len(_Catalog.inserted) == 3  # parent + both chunks
    assert len(_Vector.upserts) == 2


@pytest.mark.asyncio
async def test_document_limit_stops_before_second_parent(monkeypatch):
    async def vocab(*args, **kwargs):
        return []

    monkeypatch.setattr(pipeline_runner, "CatalogStore", _Catalog)
    monkeypatch.setattr(pipeline_runner, "VectorIndex", _Vector)
    monkeypatch.setattr(pipeline_runner, "OllamaEmbeddings", _Embeddings)
    monkeypatch.setattr(pipeline_runner, "setup_otel", lambda *args: _Tracer())
    monkeypatch.setattr(pipeline_runner, "load_vocabulary", vocab)
    monkeypatch.setattr(pipeline_runner, "is_code_path", lambda path: False)
    monkeypatch.setattr(
        pipeline_runner,
        "chunk_text",
        lambda text: [Chunk(index=0, text=text)],
    )
    cfg = openCGConfig()
    cfg.providers.extraction.enabled = False
    docs = [
        GitDocument(
            entity_id=f"parent-{index}",
            title=f"{index}.md",
            body=f"document {index}",
            source="git",
            source_uri=f"git://repo/{index}.md",
            source_revision="abc",
            content_hash=f"hash-{index}",
            metadata={"path": f"{index}.md"},
        )
        for index in range(2)
    ]

    summary = await pipeline_runner.ingest_documents(
        docs,
        cfg=cfg,
        max_documents=1,
    )

    assert summary.parents == 1
    assert summary.chunks == 1
    assert summary.documents_truncated is True
    assert len(_Catalog.inserted) == 2


@pytest.mark.asyncio
async def test_chunk_limit_stops_downstream_work(monkeypatch):
    extract_calls: list[str] = []

    async def vocab(*args, **kwargs):
        return ["related_to"]

    async def extract(**kwargs):
        extract_calls.append(kwargs["chunk_entity_id"])
        from opencg_shared import ExtractionResult

        return ExtractionResult(concepts=[], relations=[]), None

    monkeypatch.setattr(pipeline_runner, "CatalogStore", _Catalog)
    monkeypatch.setattr(pipeline_runner, "VectorIndex", _Vector)
    monkeypatch.setattr(pipeline_runner, "OllamaEmbeddings", _Embeddings)
    monkeypatch.setattr(pipeline_runner, "OllamaChat", _Chat)
    monkeypatch.setattr(pipeline_runner, "setup_otel", lambda *args: _Tracer())
    monkeypatch.setattr(pipeline_runner, "load_vocabulary", vocab)
    monkeypatch.setattr(pipeline_runner, "extract_for_chunk", extract)
    monkeypatch.setattr(pipeline_runner, "is_code_path", lambda path: False)
    monkeypatch.setattr(
        pipeline_runner,
        "chunk_text",
        lambda text: [
            Chunk(index=0, text="one"),
            Chunk(index=1, text="two"),
            Chunk(index=2, text="three"),
        ],
    )
    doc = GitDocument(
        entity_id="parent",
        title="README.md",
        body="one two three",
        source="git",
        source_uri="git://repo/README.md",
        source_revision="abc",
        content_hash="hash",
        metadata={"path": "README.md"},
    )

    summary = await pipeline_runner.ingest_documents(
        [doc],
        cfg=openCGConfig(),
        max_chunks=2,
    )

    assert summary.parents == 1
    assert summary.chunks == 2
    assert summary.chunks_truncated is True
    assert len(_Catalog.inserted) == 3
    assert len(_Vector.upserts) == 2
    assert len(extract_calls) == 2


# --- the chunker outcome reaches the runner --------------------------------


_CODE_SAMPLE = '''def parse_registry(text):
    """Pull every bare word out of the blob and hand them back."""
    words = []
    for token in text.split():
        words.append(token.strip())
    return words


def title_of(path):
    """The last path segment, minus any extension."""
    tail = path.rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[0]
'''


def _code_doc() -> GitDocument:
    return GitDocument(
        entity_id="parent",
        title="pkg/sample.py",
        body=_CODE_SAMPLE,
        source="git",
        source_uri="git://repo/pkg/sample.py",
        source_revision="abc",
        content_hash="hash",
        metadata={"path": "pkg/sample.py", "ext": ".py"},
    )


@pytest.mark.asyncio
async def test_extract_code_reports_symbols_on_the_happy_path():
    chunks, graph, outcome = await pipeline_runner._extract_code(
        _Tracer(), _code_doc(), Path("pkg/sample.py")
    )
    assert graph is not None
    assert chunks
    assert outcome == "symbols"


@pytest.mark.asyncio
async def test_inner_extract_failure_is_visible_despite_a_non_null_graph(monkeypatch):
    """`_extract_code` calls `graphify.extract` and then `chunk_code_by_symbols`
    calls it again, independently. When only the second call fails, the code
    graph is still non-null — so a caller checking `code_graph is None` would
    conclude the file was fine. The outcome is the only signal that works.
    """
    import graphify.extract as gex

    real_extract = gex.extract
    calls: list[int] = []

    def fails_on_the_inner_call(paths, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return real_extract(paths, **kwargs)
        raise RuntimeError("inner extractor exploded")

    monkeypatch.setattr(gex, "extract", fails_on_the_inner_call)

    chunks, graph, outcome = await pipeline_runner._extract_code(
        _Tracer(), _code_doc(), Path("pkg/sample.py")
    )

    assert len(calls) == 2  # the runner's own call, then the chunker's
    assert graph is not None
    assert outcome == "extract_failed"
    assert all(c.metadata.get("symbol_id") is None for c in chunks)
