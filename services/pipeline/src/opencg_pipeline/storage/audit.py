"""Audit log writer + queries."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import asyncpg
from opencg_shared.metrics import record_audit_write


def _cost_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise the cost columns for JSON: NUMERIC -> float, JSONB text -> list."""
    cost = row.get("estimated_cost_usd")
    if isinstance(cost, Decimal):
        row["estimated_cost_usd"] = float(cost)
    usage = row.get("usage_by_provider")
    if isinstance(usage, str):
        row["usage_by_provider"] = json.loads(usage)
    return row


class AuditStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _pool_required(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("AuditStore.connect() must be called first")
        return self._pool

    async def write(self, row: dict[str, Any]) -> int:
        pool = self._pool_required()
        sql = """
        INSERT INTO opencg.audit_log (
          correlation_id, tenant, principal, roles, tool, query,
          intent_plan, retriever_versions, model_versions,
          vector_collection, vector_snapshot_id,
          candidate_ids, candidate_decisions, final_entity_ids,
          final_context_hash, tokens_in, tokens_out, latency_ms,
          outcome, error_code, estimated_cost_usd, usage_by_provider
        ) VALUES (
          $1,$2,$3,$4,$5,$6,
          $7,$8,$9,
          $10,$11,
          $12,$13,$14,
          $15,$16,$17,$18,
          $19,$20,$21,$22
        )
        RETURNING id
        """
        usage = row.get("usage_by_provider")
        try:
            async with pool.acquire() as conn:
                audit_id = await conn.fetchval(
                    sql,
                    row["correlation_id"],
                    row["tenant"],
                    row["principal"],
                    row["roles"],
                    row["tool"],
                    row["query"],
                    json.dumps(row.get("intent_plan") or {}),
                    json.dumps(row.get("retriever_versions") or {}),
                    json.dumps(row.get("model_versions") or {}),
                    row.get("vector_collection"),
                    row.get("vector_snapshot_id"),
                    row.get("candidate_ids") or [],
                    json.dumps(row.get("candidate_decisions") or []),
                    row.get("final_entity_ids") or [],
                    row["final_context_hash"],
                    row.get("tokens_in", 0),
                    row.get("tokens_out", 0),
                    row.get("latency_ms", 0),
                    row.get("outcome", "ok"),
                    row.get("error_code"),
                    row.get("estimated_cost_usd"),
                    json.dumps(usage) if usage is not None else None,
                )
        except Exception:
            record_audit_write("retrieval", "error")
            raise
        record_audit_write("retrieval", "ok")
        return audit_id

    async def list_recent(self, tenant: str, limit: int = 50) -> list[dict[str, Any]]:
        pool = self._pool_required()
        sql = """
        SELECT id, created_at, correlation_id, tenant, principal, roles, tool,
               query, candidate_ids::text[] AS candidate_ids,
               final_entity_ids::text[] AS final_entity_ids,
               final_context_hash, tokens_in, tokens_out, latency_ms,
               outcome, error_code, estimated_cost_usd, usage_by_provider
        FROM opencg.audit_log
        WHERE tenant = $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, tenant, limit)
        return [_cost_fields(dict(r)) for r in rows]

    async def get(self, audit_id: int) -> dict[str, Any] | None:
        pool = self._pool_required()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, created_at, correlation_id, tenant, principal,
                          roles, tool, query, intent_plan, retriever_versions,
                          model_versions, vector_collection, vector_snapshot_id,
                          candidate_ids::text[] AS candidate_ids,
                          candidate_decisions,
                          final_entity_ids::text[] AS final_entity_ids,
                          final_context_hash, tokens_in, tokens_out,
                          latency_ms, outcome, error_code, legal_hold,
                          estimated_cost_usd, usage_by_provider
                   FROM opencg.audit_log WHERE id = $1""",
                audit_id,
            )
        return _cost_fields(dict(row)) if row else None

    async def list_for_entity(
        self, *, tenant: str, entity_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return recent retrieval audits where the entity reached final context."""
        pool = self._pool_required()
        sql = """
        SELECT id, created_at, correlation_id, tool, query, outcome
        FROM opencg.audit_log
        WHERE tenant = $1
          AND $2::uuid = ANY(final_entity_ids)
        ORDER BY created_at DESC
        LIMIT $3
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, tenant, entity_id, limit)
        return [dict(row) for row in rows]
