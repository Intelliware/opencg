from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from opencg_pipeline.storage.audit import AuditStore


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.calls.append((sql, args))
        return [
            {
                "id": 7,
                "created_at": datetime(2026, 6, 11),
                "correlation_id": "corr-7",
                "tool": "retrieve_for_context",
                "query": "prompt caching",
                "outcome": "ok",
            }
        ]


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_list_for_entity_filters_final_context_and_tenant():
    conn = _Conn()
    store = AuditStore("postgresql://unused")
    store._pool = _Pool(conn)  # type: ignore[assignment]

    rows = await store.list_for_entity(
        tenant="default", entity_id="11111111-1111-4111-8111-111111111111", limit=10
    )

    assert rows[0]["id"] == 7
    sql, args = conn.calls[0]
    assert "ANY(final_entity_ids)" in sql
    assert "tenant = $1" in sql
    assert args == ("default", "11111111-1111-4111-8111-111111111111", 10)
