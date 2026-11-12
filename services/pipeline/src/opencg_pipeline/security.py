"""Authentication and authorization for every pipeline route (add-identity-and-opa, D5, D9, D10).

`guard` is an app-wide dependency. For each request it:
1. leaves `/healthz`, `/readyz` and `/metrics` open;
2. authenticates (`request.state.auth`), or responds 401;
3. maps the route to exactly one action (`ROUTE_ACTIONS`) and asks OPA;
4. on deny writes an `access_audit_log` row and responds 403 `forbidden`;
5. on allow of a state-changing action, makes an access audit row pending. Code
   that writes the action to Postgres (graph audit, tombstone) inserts it in the
   same transaction via `take_pending_access_row()`; anything still pending when
   the handler succeeds is written on its own.
OPA failures fail closed with 503 `policy_unavailable`, except on `/retrieve`,
which must still write an `outcome = "error"` audit row: there the guard flags
`request.state.policy_unavailable` and the handler responds.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, Request
from opencg_shared import IdentityContext
from opencg_shared.auth import AuthenticatedIdentity, AuthError, unauthorized
from opencg_shared.authz import OpaClient, PolicyUnavailable, access_audit_row
from opencg_shared.metrics import record_audit_write, record_auth_failure

log = logging.getLogger(__name__)

SERVICE = "pipeline"
OPEN_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})
STATE_CHANGING = frozenset({"entity.tombstone", "graph.write", "vocab.write", "ingestion.run"})

# (method, route template) -> action. A route missing here fails
# tests/test_security.py::test_every_route_has_an_action.
ROUTE_ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/retrieve"): "retrieve",
    ("GET", "/audit/recent"): "audit.read",
    ("GET", "/audit/{audit_id}"): "audit.read",
    ("GET", "/entities"): "entity.read",
    ("GET", "/entities/{entity_id}"): "entity.read",
    ("DELETE", "/entities/{entity_id}"): "entity.tombstone",
    ("POST", "/search/vector"): "search.vector",
    ("GET", "/ingestion/connectors"): "ingestion.read",
    ("POST", "/ingestion/git/run"): "ingestion.run",
    ("GET", "/ingestion/runs/recent"): "ingestion.read",
    ("GET", "/graph/vocab"): "graph.read",
    ("GET", "/graph/concepts"): "graph.read",
    ("GET", "/graph/concepts/{concept_id}"): "graph.read",
    ("GET", "/graph/edges"): "graph.read",
    ("GET", "/graph/traverse"): "graph.read",
    ("POST", "/graph/concepts/{concept_id}/promote"): "graph.write",
    ("POST", "/graph/concepts/{concept_id}/demote"): "graph.write",
    ("DELETE", "/graph/concepts/{concept_id}"): "graph.write",
    ("PATCH", "/graph/concepts/{concept_id}"): "graph.write",
    ("POST", "/graph/concepts/merge"): "graph.write",
    ("POST", "/graph/edges/{edge_id}/promote"): "graph.write",
    ("POST", "/graph/edges/{edge_id}/demote"): "graph.write",
    ("DELETE", "/graph/edges/{edge_id}"): "graph.write",
    ("PATCH", "/graph/edges/{edge_id}"): "graph.write",
    ("POST", "/graph/vocab"): "vocab.write",
    ("PATCH", "/graph/vocab/{name}"): "vocab.write",
    ("POST", "/graph/vocab/{name}/deprecate"): "vocab.write",
}

# The pending allow row for the current request's state-changing action.
_pending: ContextVar[dict[str, Any] | None] = ContextVar("pending_access_audit", default=None)

INSERT_SQL = """
INSERT INTO opencg.access_audit_log (
  correlation_id, service, principal, roles, tenant, auth_method,
  action, resource, decision, reason, policy_package, policy_revision
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
"""


def _args(row: dict[str, Any]) -> tuple:
    return (
        row["correlation_id"],
        row["service"],
        row["principal"],
        row["roles"],
        row["tenant"],
        row["auth_method"],
        row["action"],
        row["resource"],
        row["decision"],
        row["reason"],
        row["policy_package"],
        row["policy_revision"],
    )


async def insert_access_row(conn: Any, row: dict[str, Any]) -> None:
    """Insert on an existing connection (inside the caller's transaction)."""
    await conn.execute(INSERT_SQL, *_args(row))
    record_audit_write("access", "ok")


async def write_access_row(pool: Any, row: dict[str, Any]) -> None:
    try:
        async with pool.acquire() as conn:
            await insert_access_row(conn, row)
    except Exception:
        record_audit_write("access", "error")
        log.exception("could not write access_audit_log row for %s", row.get("action"))
        raise


def take_pending_access_row() -> dict[str, Any] | None:
    """Claim the pending allow row so the caller can insert it in its own transaction."""
    row = _pending.get()
    if row is not None:
        _pending.set(None)
    return row


async def insert_pending_access_row(conn: Any) -> None:
    """For storage code: write the pending allow row (if any) in the action's transaction."""
    row = take_pending_access_row()
    if row is not None:
        await insert_access_row(conn, row)


def auth_of(request: Request) -> AuthenticatedIdentity:
    return request.state.auth


def principal_of(request: Request) -> str:
    """The authenticated principal (the stub principal in `none` mode)."""
    return auth_of(request).identity.principal


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id") or f"req-{uuid.uuid4()}"


def _resource(request: Request) -> str | None:
    params = request.path_params
    return str(next(iter(params.values()))) if params else None


def make_guard(
    service: str,
    route_actions: dict[tuple[str, str], str],
    *,
    open_paths: frozenset[str] = OPEN_PATHS,
):
    """Build the app-wide auth dependency for one service (pipeline or ingestion)."""

    async def guard(request: Request) -> AsyncIterator[None]:
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        if path in open_paths:
            yield
            return

        authenticator = request.app.state.authenticator
        try:
            auth = await authenticator.authenticate(request.headers.get("authorization"))
        except AuthError as exc:
            record_auth_failure(service, exc.code)
            log.info("authentication failed on %s: %s", path, exc.code)
            raise unauthorized(exc, authenticator.settings) from None
        request.state.auth = auth

        action = route_actions.get((request.method, path))
        if action is None:
            # Unreachable while the route-coverage tests pass; deny rather than run unchecked.
            raise HTTPException(status_code=403, detail={"code": "forbidden", "reason": "unmapped"})

        opa: OpaClient = request.app.state.opa
        resource = _resource(request)
        try:
            decision = await opa.decide(
                identity=auth.identity,
                auth_method=auth.auth_method,
                action=action,
                resource=resource,
            )
        except PolicyUnavailable as exc:
            log.warning("policy unavailable for %s: %s", action, exc)
            if action == "retrieve":
                request.state.policy_unavailable = True
                yield
                return
            raise HTTPException(
                status_code=503, detail={"code": "policy_unavailable", "message": str(exc)}
            ) from None

        row = access_audit_row(
            correlation_id=_correlation_id(request),
            service=service,
            identity=auth.identity,
            auth_method=auth.auth_method,
            action=action,
            resource=resource,
            decision=decision,
        )
        pool = request.app.state.audit_pool
        if not decision.allow:
            await write_access_row(pool, row)
            raise HTTPException(
                status_code=403, detail={"code": "forbidden", "reason": decision.reason}
            )

        if action not in STATE_CHANGING:
            yield
            return

        token = _pending.set(row)
        try:
            yield
        except Exception:
            _pending.reset(token)
            raise
        leftover = _pending.get()
        _pending.reset(token)
        if leftover is not None:
            await write_access_row(pool, leftover)

    return guard


guard = make_guard(SERVICE, ROUTE_ACTIONS)


def body_identity_or(request: Request, body_identity: IdentityContext | None) -> IdentityContext:
    """`/retrieve` identity: the token's in `oidc`/api-key mode, else the body's (or the stub)."""
    auth = auth_of(request)
    if auth.auth_method == "none" and body_identity is not None:
        return body_identity
    return auth.identity


def forward_headers(request: Request) -> dict[str, str]:
    """Headers for openCG-internal calls on behalf of this request."""
    headers: dict[str, str] = {}
    bearer = getattr(getattr(request.state, "auth", None), "bearer", None)
    if bearer:
        headers["Authorization"] = bearer
    cid = request.headers.get("x-correlation-id")
    if cid:
        headers["x-correlation-id"] = cid
    return headers
