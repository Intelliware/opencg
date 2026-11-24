"""Ingestion runner: takes a stream of GitDocuments, dispatches each file
between the symbol chunker (code) and the paragraph chunker (text), embeds
chunks via Ollama, upserts catalog rows + Qdrant points, and writes the
code graph for code files."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
from opencg_pipeline.graph.extract import extract_for_chunk
from opencg_pipeline.providers import OllamaChat, OllamaEmbeddings
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_pipeline.storage.vector import VectorIndex
from opencg_shared import openCGConfig, record_stage_tokens, setup_otel, stage_span
from opencg_shared.metrics import record_ingestion_run
from opencg_shared.otel import current_correlation_id
from opentelemetry import trace

from opencg_ingestion.chunking import chunk_code_by_symbols, chunk_text, is_code_path
from opencg_ingestion.connectors.git import GitDocument
from opencg_ingestion.graph_writer import write_code_graph
from opencg_ingestion.reextract import current_extractor_version
from opencg_ingestion.text_graph_writer import load_vocabulary, write_text_graph

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionSummary:
    parents: int
    chunks: int
    document_limit: int | None = None
    chunk_limit: int | None = None
    documents_truncated: bool = False
    chunks_truncated: bool = False

    def __iter__(self):
        yield self.parents
        yield self.chunks


async def ingest_documents(
    docs: Iterable[GitDocument],
    *,
    cfg: openCGConfig,
    max_documents: int | None = None,
    max_chunks: int | None = None,
    run_id: str | None = None,
    classification: str = "internal",
) -> IngestionSummary:
    """Ingest documents, optionally stopping at deterministic smoke/canary bounds.

    Every span of the run carries `correlation_id = run_id` (generated when
    the caller doesn't pass one).
    """
    run_id = run_id or f"ingest-{uuid.uuid4()}"
    tracer = setup_otel(
        "opencg-ingestion",
        cfg.telemetry.service_namespace,
        config_endpoint=cfg.telemetry.otlp_endpoint,
    )
    catalog = CatalogStore(cfg.postgres.url)
    vector = VectorIndex(
        url=cfg.qdrant.url,
        collection_prefix=cfg.qdrant.collection_prefix,
        vector_size=cfg.qdrant.vector_size,
        distance=cfg.qdrant.distance,
    )
    embeddings = OllamaEmbeddings(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embedding_model,
        api_key=cfg.ollama.api_key,
        provider=cfg.embeddings_endpoint().provider,
    )
    # Chat client for LLM-based text extraction. The text extractor is the
    # only caller; for code files we use graphifyy and skip chat entirely.
    chat_cfg = cfg.providers.chat
    chat: OllamaChat | None = None
    vocabulary: list[str] = []
    if cfg.providers.extraction.enabled and chat_cfg is not None:
        chat = OllamaChat(
            base_url=chat_cfg.base_url,
            model=chat_cfg.model,
            api_key=chat_cfg.api_key,
            provider=chat_cfg.provider,
        )
    await catalog.connect()
    if chat is not None:
        try:
            vocabulary = await load_vocabulary(catalog, cfg.tenant)
        except Exception as exc:
            log.warning("could not load relationship vocabulary: %s", exc)
            chat = None  # without vocab the extractor would emit garbage
    parents = 0
    chunks_total = 0
    documents_truncated = False
    chunks_truncated = False
    # One root span per run; entered by hand so the long loop below keeps its
    # indentation. Closed in the `finally`.
    run_cm = tracer.start_as_current_span("ingestion.run")
    run_span = run_cm.__enter__()
    run_span.set_attribute("correlation_id", run_id)
    run_span.set_attribute("connector", "git")
    try:
        await vector.ensure_collection("git")
        for doc_index, doc in enumerate(docs):
            if max_documents is not None and doc_index >= max_documents:
                documents_truncated = True
                break
            if max_chunks is not None and chunks_total >= max_chunks:
                chunks_truncated = True
                break
            parents += 1
            # Write parent entity (the whole file row).
            await catalog.insert_entity(
                tenant=cfg.tenant,
                entity_id=doc.entity_id,
                source=doc.source,
                source_uri=doc.source_uri,
                source_revision=doc.source_revision,
                title=doc.title,
                body=doc.body,
                content_hash=doc.content_hash,
                classification=classification,
                metadata=doc.metadata,
            )

            path = Path(doc.metadata.get("path", doc.title))
            code = is_code_path(path)

            if code:
                # Symbol-chunk + write the code graph. Failures fall back to
                # paragraph chunking and skip the graph for that file — the
                # ingest does not abort.
                chunks, code_graph = await _extract_code(tracer, doc, path)
            else:
                chunks = chunk_text(doc.body)
                code_graph = None

            for ch_index, ch in enumerate(chunks):
                if max_chunks is not None and chunks_total >= max_chunks:
                    chunks_truncated = True
                    break
                chunk_id = _chunk_id(doc, ch, ch_index, is_code=code)
                meta = {**doc.metadata, **ch.metadata, "chunk_index": ch_index}
                fragment_uri = (
                    f"{doc.source_uri}#symbol={ch.metadata['symbol_id']}"
                    if ch.metadata.get("symbol_id")
                    else f"{doc.source_uri}#chunk={ch_index}"
                )
                title_suffix = (
                    f" :: {ch.metadata['symbol_id']}"
                    if ch.metadata.get("symbol_id")
                    else f" (chunk {ch_index})"
                )
                await catalog.insert_entity(
                    tenant=cfg.tenant,
                    entity_id=chunk_id,
                    source=doc.source,
                    source_uri=fragment_uri,
                    source_revision=doc.source_revision,
                    parent_entity_id=doc.entity_id,
                    title=f"{doc.title}{title_suffix}",
                    body=ch.text,
                    content_hash=doc.content_hash,
                    classification=classification,
                    metadata=meta,
                )
                try:
                    emb = await embeddings.embed(ch.text)
                except httpx.HTTPError as exc:
                    log.error("embed failed for %s chunk %d: %s", doc.source_uri, ch_index, exc)
                    continue
                record_stage_tokens(
                    stage="ingest_embed",
                    tenant=cfg.tenant,
                    tokens_in=emb.tokens_in,
                    tokens_out=0,
                    model=emb.model,
                    provider=emb.provider,
                )
                payload = {
                    "tenant": cfg.tenant,
                    "entity_id": chunk_id,
                    "parent_entity_id": doc.entity_id,
                    "source": "git",
                    "source_uri": doc.source_uri,
                    "title": doc.title,
                    "text": ch.text,
                    "classification": classification,
                    "chunk_index": ch_index,
                }
                if ch.metadata.get("symbol_id"):
                    payload["symbol_id"] = ch.metadata["symbol_id"]
                await vector.upsert(
                    source="git",
                    entity_id=chunk_id,
                    vector=emb.vector,
                    payload=payload,
                )
                chunks_total += 1

                # LLM-based text extraction. Code chunks are skipped because
                # the deterministic graphifyy result for the whole file is
                # written below. For text chunks (markdown, yaml, etc.), each
                # chunk individually gets the LLM extractor. Best-effort —
                # a failed chunk doesn't abort the loop.
                if not code and chat is not None and vocabulary:
                    try:
                        result, _telemetry = await extract_for_chunk(
                            chunk_text=ch.text,
                            chunk_entity_id=chunk_id,
                            vocabulary=vocabulary,
                            chat=chat,
                            tenant=cfg.tenant,
                            min_confidence=cfg.providers.extraction.min_confidence,
                            timeout_seconds=cfg.providers.extraction.timeout_seconds,
                        )
                        if result.concepts or result.relations:
                            await write_text_graph(
                                catalog=catalog,
                                tenant=cfg.tenant,
                                chunk_entity_id=chunk_id,
                                result=result,
                                extractor_version=current_extractor_version(chat.model),
                            )
                    except Exception as exc:
                        log.info(
                            "text extractor skipped for %s chunk %d: %s",
                            doc.source_uri,
                            ch_index,
                            exc,
                        )

            # Persist the graph for code files. Best-effort — a graph write
            # failure must NOT roll back the chunk inserts above.
            if code and code_graph is not None:
                try:
                    await write_code_graph(
                        catalog=catalog,
                        tenant=cfg.tenant,
                        file_entity_id=doc.entity_id,
                        graphify_result=code_graph,
                    )
                except Exception as exc:
                    log.warning("graph_writer failed for %s: %s", doc.source_uri, exc)
    finally:
        run_span.set_attribute("documents", parents)
        run_span.set_attribute("chunks", chunks_total)
        run_cm.__exit__(None, None, None)
        await catalog.close()
        await vector.close()
        await embeddings.close()
        if chat is not None:
            await chat.close()
    return IngestionSummary(
        parents=parents,
        chunks=chunks_total,
        document_limit=max_documents,
        chunk_limit=max_chunks,
        documents_truncated=documents_truncated,
        chunks_truncated=chunks_truncated,
    )


def _safe_relpath(doc: GitDocument, path: Path) -> Path:
    """The repo-relative path under which to materialise a code file.

    graphifyy derives node labels and symbol ids from the file path, so we
    must preserve the real name. The git connector only carries a relative
    path (`doc.metadata["path"]`), which may contain a leading `/` or `..`
    segments; strip those so the join can never escape the temp directory.
    """
    raw = doc.metadata.get("path") or doc.title or path.name or "file"
    parts = [p for p in Path(raw).parts if p not in ("", ".", "..", "/", "\\")]
    return Path(*parts) if parts else Path(path.name or "file")


@contextlib.contextmanager
def _materialised_code_path(doc: GitDocument, path: Path) -> Iterator[Path]:
    """Yield an on-disk path graphifyy can read, named after the real source.

    The git connector hands us only a body and a repo-relative path — never an
    on-disk location — so for code files we write the body under its true
    relative path inside a throwaway temp directory. If `path` is already a
    genuine absolute file on disk (a future connector might provide one), we
    pass it straight through without copying. The temp tree is always removed,
    including when the caller raises.
    """
    if path.is_absolute() and path.exists():
        yield path
        return

    tmpdir = tempfile.mkdtemp(prefix="opencg-code-")
    try:
        dest = Path(tmpdir) / _safe_relpath(doc, path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(doc.body, encoding="utf-8")
        yield dest
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def _extract_code(
    tracer: trace.Tracer, doc: GitDocument, path: Path
) -> tuple[list, dict | None]:
    """Run the symbol chunker AND capture the raw graphify result.

    Wrapped in an OTel span (`pipeline.graph_extract_code`) with zero token
    counts so observability tooling sees the deterministic extractor.
    Failures fall back to text chunking for embedding and skip the graph.
    """
    import graphify
    import graphify.extract as gex

    start = time.perf_counter()
    with stage_span(tracer, "pipeline.graph_extract_code", current_correlation_id()) as span:
        span.set_attribute("model", "graphifyy")
        span.set_attribute("provider", "graphifyy")
        span.set_attribute(
            "extractor_version", f"graphifyy/{getattr(graphify, '__version__', '0.0.0')}"
        )
        span.set_attribute("tokens_in", 0)
        span.set_attribute("tokens_out", 0)
        try:
            # graphifyy names nodes/symbols after the file path, so materialise
            # the body under its real repo-relative name (the temp tree is torn
            # down when the context exits — including on the failure path below).
            with _materialised_code_path(doc, path) as use_path:
                graphify_result = gex.extract([use_path], parallel=False)
                chunks = chunk_code_by_symbols(use_path, doc.body)
                span.set_attribute("symbols", len(graphify_result.get("nodes", [])))
                span.set_attribute("chunks", len(chunks))
        except Exception as exc:
            log.warning("graphifyy failed for %s: %s; using text chunker", doc.source_uri, exc)
            span.record_exception(exc)
            return chunk_text(doc.body), None
        span.set_attribute("latency_ms", int((time.perf_counter() - start) * 1000))
        return chunks, graphify_result


_CHUNK_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000002")
_SYMBOL_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000003")


def _chunk_id(doc: GitDocument, ch, ch_index: int, *, is_code: bool) -> str:
    """Stable chunk id derivation.

    Text chunks: `uuid5(_CHUNK_NS, "{parent_id}:{index}")`.
    Symbol chunks: `uuid5(_SYMBOL_NS, "{parent_id}:{symbol_id}[:{index}]")` —
        the trailing index is used only when a single symbol was paragraph-
        split (so each sub-chunk gets a unique id).
    """
    symbol_id = ch.metadata.get("symbol_id") if ch.metadata else None
    if is_code and symbol_id:
        # Big symbols get split — disambiguate via index when `split=True`.
        key = (
            f"{doc.entity_id}:{symbol_id}:{ch_index}"
            if ch.metadata.get("split")
            else f"{doc.entity_id}:{symbol_id}"
        )
        return str(uuid.uuid5(_SYMBOL_NS, key))
    return str(uuid.uuid5(_CHUNK_NS, f"{doc.entity_id}:{ch_index}"))


async def run(
    repo_url: str,
    cfg: openCGConfig,
    *,
    max_documents: int | None = None,
    max_chunks: int | None = None,
    run_id: str | None = None,
    classification: str = "internal",
) -> IngestionSummary:
    """Clone, walk and ingest one repository; counts the run per connector."""
    from opencg_ingestion.connectors.git import ingest_repo

    started = time.perf_counter()
    try:
        docs = list(ingest_repo(repo_url, cfg.tenant))
        log.info("ingesting %d documents from %s", len(docs), repo_url)
        summary = await ingest_documents(
            docs,
            cfg=cfg,
            max_documents=max_documents,
            max_chunks=max_chunks,
            run_id=run_id,
            classification=classification,
        )
    except BaseException:
        record_ingestion_run(
            connector="git", status="failed", duration_seconds=time.perf_counter() - started
        )
        raise
    record_ingestion_run(
        connector="git",
        status="succeeded",
        documents=summary.parents,
        chunks=summary.chunks,
        duration_seconds=time.perf_counter() - started,
    )
    return summary


def run_sync(
    repo_url: str,
    cfg: openCGConfig,
    *,
    max_documents: int | None = None,
    max_chunks: int | None = None,
    classification: str = "internal",
) -> IngestionSummary:
    return asyncio.run(
        run(
            repo_url,
            cfg,
            max_documents=max_documents,
            max_chunks=max_chunks,
            classification=classification,
        )
    )
