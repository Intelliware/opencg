"""Schema readiness (`/readyz` fails when a later init script was not applied)."""

from __future__ import annotations

import pytest
from opencg_pipeline.storage import schema

pytestmark = pytest.mark.asyncio


class _Conn:
    def __init__(self, columns: set[tuple[str, str]]) -> None:
        self._columns = columns
        self.calls: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args):
        self.calls.append((sql, args))
        return [
            {"table_schema": "opencg", "table_name": t, "column_name": c}
            for (t, c) in sorted(self._columns)
            if t in args[0]
        ]


FULL = {
    ("audit_log", "id"),
    ("audit_log", "estimated_cost_usd"),
    ("audit_log", "usage_by_provider"),
    ("audit_log", "auth_method"),
    ("access_audit_log", "id"),
}


async def test_current_schema_is_ready():
    assert await schema.missing_schema(_Conn(FULL)) == {}


async def test_missing_auth_method_column_names_070():
    missing = await schema.missing_schema(_Conn(FULL - {("audit_log", "auth_method")}))
    assert missing == {"070_access_audit.sql": ["opencg.audit_log.auth_method"]}
    assert "make db-apply SQL=070_access_audit.sql" in schema.describe(missing)


async def test_missing_cost_columns_name_060():
    conn = _Conn(FULL - {("audit_log", "estimated_cost_usd"), ("audit_log", "usage_by_provider")})
    missing = await schema.missing_schema(conn)
    assert missing == {
        "060_audit_cost.sql": [
            "opencg.audit_log.estimated_cost_usd",
            "opencg.audit_log.usage_by_provider",
        ]
    }


async def test_missing_access_audit_table():
    missing = await schema.missing_schema(_Conn({c for c in FULL if c[0] != "access_audit_log"}))
    assert missing == {"070_access_audit.sql": ["opencg.access_audit_log"]}


async def test_pre_060_volume_names_both_scripts():
    missing = await schema.missing_schema(_Conn({("audit_log", "id")}))
    assert set(missing) == {"060_audit_cost.sql", "070_access_audit.sql"}
    detail = schema.describe(missing)
    assert detail.index("060_audit_cost.sql") < detail.index("070_access_audit.sql")
