"""Schema readiness: the tables and columns later init scripts add.

`infra/postgres/init/*` runs only when a volume is first created, so an existing
volume can be missing a later script. Without this check the service reports
ready and then fails on its first write (for example, `/retrieve` returning 500
because `audit_log.estimated_cost_usd` does not exist). `/readyz` calls
`missing_schema()` and names the script to apply.
"""

from __future__ import annotations

from typing import Any

# (schema, table, column or None for the table itself) -> the script that adds it.
REQUIRED: dict[tuple[str, str, str | None], str] = {
    ("opencg", "audit_log", "estimated_cost_usd"): "060_audit_cost.sql",
    ("opencg", "audit_log", "usage_by_provider"): "060_audit_cost.sql",
    ("opencg", "access_audit_log", None): "070_access_audit.sql",
    ("opencg", "audit_log", "auth_method"): "070_access_audit.sql",
}

_PRESENT_SQL = """
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'opencg' AND table_name = ANY($1::text[])
"""


async def missing_schema(conn: Any) -> dict[str, list[str]]:
    """Script -> missing objects (`table` or `table.column`); empty when all present."""
    tables = sorted({t for (_, t, _) in REQUIRED})
    rows = await conn.fetch(_PRESENT_SQL, tables)
    present_columns = {(r["table_schema"], r["table_name"], r["column_name"]) for r in rows}
    present_tables = {(s, t) for (s, t, _) in present_columns}
    missing: dict[str, list[str]] = {}
    for (schema, table, column), script in REQUIRED.items():
        ok = (
            (schema, table) in present_tables
            if column is None
            else (schema, table, column) in present_columns
        )
        if not ok:
            missing.setdefault(script, []).append(
                f"{schema}.{table}" if column is None else f"{schema}.{table}.{column}"
            )
    return missing


def describe(missing: dict[str, list[str]]) -> str:
    parts = [
        f"{', '.join(objs)} missing; apply infra/postgres/init/{script} "
        f"(make db-apply SQL={script})"
        for script, objs in sorted(missing.items())
    ]
    return "postgres: " + "; ".join(parts)
