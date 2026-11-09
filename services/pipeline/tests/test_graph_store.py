from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from opencg_pipeline.storage.graph import GraphStore, _reachable_ids


class _Tx:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        self.conn.tx_started = True
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.conn.tx_finished = True
        self.conn.rolled_back = exc_type is not None


class _Conn:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.rows = list(rows)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.tx_started = False
        self.tx_finished = False
        self.rolled_back = False

    async def fetchrow(self, sql: str, *args: Any):
        self.calls.append((sql, args))
        return self.rows.pop(0)

    async def execute(self, sql: str, *args: Any):
        self.calls.append((sql, args))

    def transaction(self) -> _Tx:
        return _Tx(self)


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self.conn)


def _store(conn: _Conn) -> GraphStore:
    store = GraphStore("postgresql://unused")
    store._pool = _Pool(conn)  # type: ignore[assignment]
    return store


def _edge(state: str) -> dict[str, Any]:
    now = datetime(2026, 6, 12)
    return {
        "edge_id": "e1",
        "tenant": "default",
        "type": "depends_on",
        "from_concept_id": "c1",
        "to_concept_id": "c2",
        "state": state,
        "confidence": 0.9,
        "extractor_version": "test",
        "created_at": now,
        "updated_at": now,
        "tombstoned_at": None,
    }


@pytest.mark.asyncio
async def test_edge_transition_reflects_age_and_writes_audit_in_transaction():
    conn = _Conn([_edge("candidate"), _edge("confirmed")])
    result = await _store(conn).transition_edge(
        tenant="default",
        edge_id="e1",
        state="confirmed",
        actor="alice",
        reason="reviewed",
    )

    assert result is not None and result["state"] == "confirmed"
    assert conn.tx_started and conn.tx_finished and not conn.rolled_back
    sql = "\n".join(call[0] for call in conn.calls)
    assert "UPDATE opencg.relationship_edge" in sql
    assert "ag_catalog.cypher" in sql
    assert "ag_catalog.agtype" in sql
    assert "INSERT INTO opencg.graph_audit_log" in sql
    audit_args = next(
        args for statement, args in conn.calls if "INSERT INTO opencg.graph_audit_log" in statement
    )
    assert audit_args[:7] == (
        "alice",
        "default",
        "edge",
        "e1",
        "candidate",
        "confirmed",
        "reviewed",
    )


@pytest.mark.asyncio
async def test_idempotent_edge_transition_does_not_write_audit():
    conn = _Conn([_edge("confirmed")])
    result = await _store(conn).transition_edge(
        tenant="default",
        edge_id="e1",
        state="confirmed",
        actor="alice",
        reason="again",
    )

    assert result is not None and result["state"] == "confirmed"
    assert not any("INSERT INTO opencg.graph_audit_log" in statement for statement, _ in conn.calls)


@pytest.mark.asyncio
async def test_age_failure_rolls_back_transition(monkeypatch):
    conn = _Conn([_edge("candidate"), _edge("confirmed")])

    async def fail_age(*args, **kwargs):
        raise RuntimeError("AGE failure")

    monkeypatch.setattr(
        "opencg_pipeline.storage.graph.reflect_edge",
        fail_age,
    )
    with pytest.raises(RuntimeError, match="AGE failure"):
        await _store(conn).transition_edge(
            tenant="default",
            edge_id="e1",
            state="confirmed",
            actor="alice",
            reason="reviewed",
        )

    assert conn.rolled_back


def test_reachable_ids_supports_mixed_edge_states_after_sql_filtering():
    edges = [
        {"from_concept_id": "c1", "to_concept_id": "c2"},
        {"from_concept_id": "c2", "to_concept_id": "c3"},
        {"from_concept_id": "unreachable", "to_concept_id": "c4"},
    ]

    assert _reachable_ids(
        concept_id="c1",
        edges=edges,
        depth=2,
        limit=50,
    ) == ["c1", "c2", "c3"]


def test_reachable_ids_respects_depth_and_limit():
    edges = [
        {"from_concept_id": "c1", "to_concept_id": "c2"},
        {"from_concept_id": "c1", "to_concept_id": "c3"},
        {"from_concept_id": "c2", "to_concept_id": "c4"},
    ]

    assert _reachable_ids(
        concept_id="c1",
        edges=edges,
        depth=1,
        limit=2,
    ) == ["c1", "c2"]
    assert _reachable_ids(
        concept_id="c1",
        edges=edges,
        depth=4,
        limit=1,
    ) == ["c1"]
