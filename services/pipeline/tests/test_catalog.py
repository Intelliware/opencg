from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from opencg_pipeline.storage.catalog import CatalogStore


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Conn:
    """Records SQL + args so tests can assert on what was sent."""

    def __init__(
        self,
        *,
        fetch_rows: list[list[dict[str, Any]]] | None = None,
        fetchrow_rows: list[dict[str, Any] | None] | None = None,
        fetchval_rows: list[Any] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self._fetch = list(fetch_rows or [])
        self._fetchrow = list(fetchrow_rows or [])
        self._fetchval = list(fetchval_rows or [])

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.calls.append(("fetch", sql, args))
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.calls.append(("fetchrow", sql, args))
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchval", sql, args))
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql: str, *args: Any) -> None:
        self.calls.append(("execute", sql, args))


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


def _store_with(conn: _Conn) -> CatalogStore:
    store = CatalogStore("postgresql://unused")
    store._pool = _Pool(conn)  # type: ignore[assignment]
    return store


@pytest.mark.asyncio
async def test_list_entities_no_filters():
    conn = _Conn(
        fetch_rows=[
            [
                {
                    "entity_id": "e1",
                    "tenant": "default",
                    "source": "git",
                    "source_uri": "git://x/README.md",
                    "title": "README.md",
                    "classification": "internal",
                    "freshness_state": "fresh",
                    "updated_at": datetime(2026, 6, 11),
                    "tombstoned_at": None,
                }
            ]
        ],
        fetchval_rows=[1],
    )
    rows, total = await _store_with(conn).list_entities(tenant="default")

    assert total == 1
    assert rows[0]["entity_id"] == "e1"

    list_sql = conn.calls[0][1]
    assert "tenant = $1" in list_sql
    assert "source = " not in list_sql
    # Pagination params come after the tenant arg.
    assert conn.calls[0][2] == ("default", 50, 0)


@pytest.mark.asyncio
async def test_list_entities_all_filters_param_ordering():
    conn = _Conn(fetch_rows=[[]], fetchval_rows=[0])
    await _store_with(conn).list_entities(
        tenant="default",
        source="git",
        classification="internal",
        freshness_state="fresh",
        limit=10,
        offset=20,
    )

    sql, args = conn.calls[0][1], conn.calls[0][2]
    assert "source = $2" in sql
    assert "classification = $3" in sql
    assert "freshness_state = $4" in sql
    assert "LIMIT $5 OFFSET $6" in sql
    assert args == ("default", "git", "internal", "fresh", 10, 20)


@pytest.mark.asyncio
async def test_get_entity_with_lineage_parent_and_children():
    parent_id = "p1"
    chunk_row = {
        "entity_id": "c1",
        "tenant": "default",
        "source": "git",
        "source_uri": "git://x/file#chunk=0",
        "source_revision": "abc",
        "parent_entity_id": parent_id,
        "title": "file (chunk 0)",
        "body": "chunk body",
        "content_hash": "h",
        "classification": "internal",
        "freshness_state": "fresh",
        "metadata": json.dumps({"chunk_index": 0}),
        "created_at": datetime(2026, 6, 11),
        "updated_at": datetime(2026, 6, 11),
        "ingested_at": datetime(2026, 6, 11),
        "last_verified_at": datetime(2026, 6, 11),
        "tombstoned_at": None,
    }
    parent_ref = {"entity_id": parent_id, "title": "file", "source_uri": "git://x/file"}
    conn = _Conn(
        fetchrow_rows=[chunk_row, parent_ref],
        fetch_rows=[[]],  # no children
    )
    out = await _store_with(conn).get_entity_with_lineage(tenant="default", entity_id="c1")

    assert out is not None
    assert out["entity_id"] == "c1"
    # Metadata is decoded from JSON string into dict.
    assert out["metadata"] == {"chunk_index": 0}
    assert out["lineage"]["parent"]["entity_id"] == parent_id
    assert out["lineage"]["children"] == []


@pytest.mark.asyncio
async def test_get_entity_with_lineage_parent_with_chunks():
    parent_row = {
        "entity_id": "p1",
        "tenant": "default",
        "source": "git",
        "source_uri": "git://x/file",
        "source_revision": "abc",
        "parent_entity_id": None,
        "title": "file",
        "body": "full body",
        "content_hash": "h",
        "classification": "internal",
        "freshness_state": "fresh",
        "metadata": "{}",
        "created_at": datetime(2026, 6, 11),
        "updated_at": datetime(2026, 6, 11),
        "ingested_at": datetime(2026, 6, 11),
        "last_verified_at": datetime(2026, 6, 11),
        "tombstoned_at": None,
    }
    children = [
        {"entity_id": "c1", "title": "file (chunk 0)", "source_uri": "git://x/file#chunk=0"},
        {"entity_id": "c2", "title": "file (chunk 1)", "source_uri": "git://x/file#chunk=1"},
    ]
    conn = _Conn(fetchrow_rows=[parent_row], fetch_rows=[children])

    out = await _store_with(conn).get_entity_with_lineage(tenant="default", entity_id="p1")

    assert out is not None
    assert out["lineage"]["parent"] is None
    assert len(out["lineage"]["children"]) == 2
    assert out["lineage"]["children"][0]["entity_id"] == "c1"


@pytest.mark.asyncio
async def test_get_entity_with_lineage_missing_returns_none():
    conn = _Conn(fetchrow_rows=[None])
    out = await _store_with(conn).get_entity_with_lineage(tenant="default", entity_id="missing")
    assert out is None


@pytest.mark.asyncio
async def test_tombstone_idempotent_uses_coalesce():
    conn = _Conn(
        fetchrow_rows=[
            {
                "entity_id": "e1",
                "tenant": "default",
                "source": "git",
                "source_uri": "git://x/y",
                "title": "y",
                "classification": "internal",
                "freshness_state": "fresh",
                "updated_at": datetime(2026, 6, 11),
                "tombstoned_at": datetime(2026, 6, 11),
            }
        ]
    )
    out = await _store_with(conn).tombstone(tenant="default", entity_id="e1")
    assert out is not None and out["tombstoned_at"] is not None
    # COALESCE means re-tombstoning preserves the original timestamp.
    assert "COALESCE(tombstoned_at, now())" in conn.calls[0][1]


@pytest.mark.asyncio
async def test_tombstone_missing_returns_none():
    conn = _Conn(fetchrow_rows=[None])
    out = await _store_with(conn).tombstone(tenant="default", entity_id="missing")
    assert out is None


@pytest.mark.asyncio
async def test_get_evidence_chunks_returns_entity_refs():
    conn = _Conn(
        fetch_rows=[
            [
                {
                    "entity_id": "chunk-1",
                    "title": "README (chunk 0)",
                    "source_uri": "git://repo/README.md#chunk=0",
                }
            ]
        ]
    )
    rows = await _store_with(conn).get_evidence_chunks(tenant="default", edge_id="edge-1")

    assert rows == [
        {
            "entity_id": "chunk-1",
            "title": "README (chunk 0)",
            "source_uri": "git://repo/README.md#chunk=0",
        }
    ]
    assert conn.calls[0][2] == ("default", "edge-1")
