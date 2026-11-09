from __future__ import annotations

from dataclasses import dataclass

import pytest
from opencg_ingestion import pipeline_runner
from opencg_ingestion.chunking import Chunk
from opencg_ingestion.connectors.git import GitDocument
from opencg_pipeline.providers import EmbeddingResult
from opencg_shared import openCGConfig


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
        raise TimeoutError("slow model")

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
