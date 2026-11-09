from __future__ import annotations

import pytest
from opencg_ingestion import text_graph_writer
from opencg_ingestion.text_graph_writer import write_text_graph
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_shared import ExtractionResult


class _Tx:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        self._conn.tx_started = True
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._conn.tx_finished = True
        self._conn.rolled_back = exc_type is not None


class _Conn:
    def __init__(
        self,
        returned_concepts: list[dict[str, str]] | None = None,
        returned_edges: list[dict[str, object]] | None = None,
    ) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.returned_concepts = list(returned_concepts or [])
        self.returned_edges = list(returned_edges or [])
        self.tx_started = False
        self.tx_finished = False
        self.rolled_back = False

    async def execute(self, sql: str, *args: object) -> None:
        self.statements.append((sql, args))

    async def fetchrow(self, sql: str, *args: object) -> dict[str, object]:
        self.statements.append((sql, args))
        if "INSERT INTO opencg.relationship_edge" in sql:
            if self.returned_edges:
                return self.returned_edges.pop(0)
            return {
                "edge_id": str(args[0]),
                "state": "candidate",
                "confidence": args[6],
            }
        if self.returned_concepts:
            return self.returned_concepts.pop(0)
        return {"concept_id": str(args[0]), "state": "candidate"}

    def transaction(self) -> _Tx:
        return _Tx(self)


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


def _catalog(conn: _Conn) -> CatalogStore:
    catalog = CatalogStore("postgresql://unused")
    catalog._pool = _Pool(conn)  # type: ignore[assignment]
    return catalog


def _result() -> ExtractionResult:
    return ExtractionResult.model_validate(
        {
            "concepts": [
                {
                    "name": " Prompt   Caching ",
                    "description": "Caches model prompts.",
                    "aliases": ["prompt cache"],
                },
                {"name": "Token Store"},
            ],
            "relations": [
                {
                    "from": "Prompt Caching",
                    "relation": "depends_on",
                    "to": "Token Store",
                    "evidence_span": "Prompt caching depends on the token store.",
                    "confidence": 0.9,
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_writes_normalized_concepts_edge_evidence_and_age():
    conn = _Conn()
    concepts, edges = await write_text_graph(
        catalog=_catalog(conn),
        tenant="default",
        chunk_entity_id="chunk-1",
        result=_result(),
        extractor_version="text-extractor/gemma3:4b",
    )

    assert (concepts, edges) == (2, 1)
    concept_insert = next(
        args for sql, args in conn.statements if "INSERT INTO opencg.concept" in sql
    )
    assert concept_insert[3] == "prompt caching"
    assert concept_insert[5] == ["prompt cache"]
    assert any("ag_catalog.cypher" in sql for sql, _ in conn.statements)
    assert any("INSERT INTO opencg.relationship_evidence" in sql for sql, _ in conn.statements)
    assert conn.tx_started and conn.tx_finished and not conn.rolled_back


@pytest.mark.asyncio
async def test_uses_authoritative_concept_ids_after_dedupe_conflict():
    conn = _Conn(
        returned_concepts=[
            {"concept_id": "existing-code-id", "state": "confirmed"},
            {"concept_id": "stored-token-id", "state": "candidate"},
        ],
        returned_edges=[
            {
                "edge_id": "existing-code-edge",
                "state": "confirmed",
                "confidence": 1.0,
            }
        ],
    )
    await write_text_graph(
        catalog=_catalog(conn),
        tenant="default",
        chunk_entity_id="chunk-1",
        result=_result(),
        extractor_version="text-extractor/test",
    )

    edge_insert = next(
        args for sql, args in conn.statements if "INSERT INTO opencg.relationship_edge" in sql
    )
    assert edge_insert[3:5] == ("existing-code-id", "stored-token-id")
    evidence_insert = next(
        args for sql, args in conn.statements if "INSERT INTO opencg.relationship_evidence" in sql
    )
    assert evidence_insert[0] == "existing-code-edge"
    reflected = [args[0] for sql, args in conn.statements if "MERGE (concept:Concept" in sql]
    assert '"concept_id": "existing-code-id"' in reflected[0]
    assert '"state": "confirmed"' in reflected[0]
    edge_reflection = next(
        args[0] for sql, args in conn.statements if "MERGE (source)-[edge:depends_on" in sql
    )
    assert '"edge_id": "existing-code-edge"' in edge_reflection
    assert '"state": "confirmed"' in edge_reflection


@pytest.mark.asyncio
async def test_invalid_vocabulary_name_rolls_back_transaction():
    conn = _Conn()
    result = _result()
    result.relations[0].relation = "not-valid"

    with pytest.raises(ValueError, match="invalid AGE edge label"):
        await write_text_graph(
            catalog=_catalog(conn),
            tenant="default",
            chunk_entity_id="chunk-1",
            result=result,
            extractor_version="text-extractor/test",
        )

    assert conn.rolled_back


@pytest.mark.asyncio
async def test_age_failure_rolls_back_transaction(monkeypatch):
    conn = _Conn()

    async def fail_age(*args, **kwargs):
        raise RuntimeError("AGE unavailable")

    monkeypatch.setattr(text_graph_writer, "reflect_edge", fail_age)

    with pytest.raises(RuntimeError, match="AGE unavailable"):
        await write_text_graph(
            catalog=_catalog(conn),
            tenant="default",
            chunk_entity_id="chunk-1",
            result=_result(),
            extractor_version="text-extractor/test",
        )

    assert conn.rolled_back
