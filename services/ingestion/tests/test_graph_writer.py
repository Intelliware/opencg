"""Unit tests for the graph_writer module.

A fake asyncpg pool/connection/transaction captures every SQL statement so
we can assert on intent (vocabulary mapping, confidence buckets, idempotent
upsert paths) without standing up Postgres.
"""

from __future__ import annotations

import pytest
from opencg_ingestion.graph_writer import (
    _CONFIDENCE_MAP,
    _RELATION_MAP,
    write_code_graph,
)
from opencg_pipeline.storage.catalog import CatalogStore

# --- fakes -----------------------------------------------------------------


class _Tx:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        self._conn.tx_started = True
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        self._conn.tx_finished = True
        return None


class _Conn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []
        self.tx_started = False
        self.tx_finished = False

    async def execute(self, sql: str, *args: object) -> None:
        self.statements.append((sql, args))

    def transaction(self) -> _Tx:
        return _Tx(self)


class _Acq:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def acquire(self) -> _Acq:
        return _Acq(self._conn)


def _store_with(conn: _Conn) -> CatalogStore:
    s = CatalogStore("postgresql://unused")
    s._pool = _Pool(conn)  # type: ignore[assignment]
    return s


# --- tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_node_writes_one_concept():
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {
                "id": "mod_alpha",
                "label": "alpha()",
                "file_type": "code",
                "_origin": "ast",
                "source_file": "x.py",
                "source_location": "L1",
            }
        ],
        "edges": [],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    assert concepts == 1
    assert edges == 0
    # First insert is the concept; transaction is bracketed.
    assert conn.tx_started and conn.tx_finished
    assert any("INSERT INTO opencg.concept" in s for s, _ in conn.statements)


@pytest.mark.asyncio
async def test_extracted_edge_lands_confirmed():
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "a", "label": "A()", "file_type": "code", "_origin": "ast"},
            {"id": "b", "label": "B()", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_location": "L7",
            }
        ],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    assert concepts == 2
    assert edges == 1
    edge_inserts = [
        (sql, args)
        for sql, args in conn.statements
        if "INSERT INTO opencg.relationship_edge" in sql
    ]
    assert len(edge_inserts) == 1
    args = edge_inserts[0][1]
    # Arg ordering matches the SQL: edge_id, tenant, type, from, to,
    # state, confidence, extractor_version.
    state = args[5]
    confidence = args[6]
    assert state == "confirmed"
    assert confidence == 1.0


@pytest.mark.asyncio
async def test_ambiguous_edge_lands_candidate():
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "a", "label": "A()", "file_type": "code", "_origin": "ast"},
            {"id": "b", "label": "B()", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "AMBIGUOUS",
            }
        ],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    assert edges == 1
    edge_inserts = [a for s, a in conn.statements if "INSERT INTO opencg.relationship_edge" in s]
    state = edge_inserts[0][5]
    confidence = edge_inserts[0][6]
    assert state == "candidate"
    assert confidence == 0.5


@pytest.mark.asyncio
async def test_inferred_edge_confirmed_at_lower_confidence():
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "a", "label": "A()", "file_type": "code", "_origin": "ast"},
            {"id": "b", "label": "B()", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [{"source": "a", "target": "b", "relation": "uses", "confidence": "INFERRED"}],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    assert edges == 1
    edge_args = next(a for s, a in conn.statements if "INSERT INTO opencg.relationship_edge" in s)
    assert edge_args[5] == "confirmed"
    assert edge_args[6] == 0.85


@pytest.mark.asyncio
async def test_relations_map_to_vocabulary():
    """contains/method → defined_in; imports_from → imports."""
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "f", "label": "F()", "file_type": "code", "_origin": "ast"},
            {"id": "c", "label": "C", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {"source": "f", "target": "c", "relation": "contains", "confidence": "EXTRACTED"},
            {"source": "f", "target": "c", "relation": "method", "confidence": "EXTRACTED"},
            {"source": "f", "target": "c", "relation": "imports_from", "confidence": "EXTRACTED"},
            {"source": "f", "target": "c", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "f", "target": "c", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "f", "target": "c", "relation": "uses", "confidence": "EXTRACTED"},
        ],
    }
    await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    edge_args = [a for s, a in conn.statements if "INSERT INTO opencg.relationship_edge" in s]
    types = [args[2] for args in edge_args]
    # Each mapping verified per the _RELATION_MAP table.
    expected_types = {"defined_in", "imports", "calls", "uses"}
    assert set(types) == expected_types


@pytest.mark.asyncio
async def test_unknown_relation_dropped():
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "_origin": "ast"},
            {"id": "b", "label": "B", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {"source": "a", "target": "b", "relation": "smells_like", "confidence": "EXTRACTED"},
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    assert edges == 1  # unknown relation skipped


@pytest.mark.asyncio
async def test_external_target_becomes_concept_on_the_fly():
    """`imports os` creates the `os` concept even though it isn't a node."""
    conn = _Conn()
    catalog = _store_with(conn)
    result = {
        "nodes": [
            {"id": "mod", "label": "mod.py", "file_type": "code", "_origin": "ast"},
        ],
        "edges": [
            {"source": "mod", "target": "os", "relation": "imports", "confidence": "EXTRACTED"},
        ],
    }
    concepts, edges = await write_code_graph(
        catalog=catalog,
        tenant="t",
        file_entity_id="file-uuid",
        graphify_result=result,
    )
    # 1 node concept + 1 external target concept (os) = 2.
    assert concepts == 2
    assert edges == 1


def test_relation_map_covers_documented_set():
    """Sanity: the mapping table covers everything we documented in design.md."""
    assert set(_RELATION_MAP.keys()) == {
        "calls",
        "imports",
        "imports_from",
        "contains",
        "method",
        "uses",
    }


def test_confidence_map_covers_three_labels():
    assert set(_CONFIDENCE_MAP.keys()) == {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
    assert _CONFIDENCE_MAP["EXTRACTED"] == ("confirmed", 1.0)
    assert _CONFIDENCE_MAP["AMBIGUOUS"][0] == "candidate"
