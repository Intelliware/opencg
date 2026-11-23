"""Test doubles for the auth guard: an authenticator, OPA and an access-audit pool.

Used by the pipeline and ingestion test suites; not imported by service code.
"""

from __future__ import annotations

from typing import Any

from opencg_shared.auth import Authenticator, settings_from_env
from opencg_shared.authz import AdminDecision, Decision, EntitlementResult, PolicyUnavailable


def authenticator(**env: str) -> Authenticator:
    base = {"OPENCG__AUTH__MODE": "none", "OPENCG__ENVIRONMENT": "dev"}
    base.update(env)
    return Authenticator(
        settings_from_env(
            tenant="default", stub_principal="local-dev", stub_roles=["admin", "reader"], env=base
        )
    )


class FakeOpa:
    """Allows everything unless told otherwise; records calls."""

    def __init__(
        self,
        *,
        deny_actions: set[str] | None = None,
        deny_classifications: set[str] | None = None,
        unavailable: bool = False,
        entitle_unavailable: bool = False,
    ) -> None:
        self.deny_actions = deny_actions or set()
        self.deny_classifications = deny_classifications or set()
        self.unavailable = unavailable
        self.entitle_unavailable = entitle_unavailable
        self.entitle_calls: list[dict[str, Any]] = []
        self.decide_calls: list[dict[str, Any]] = []

    async def ready(self) -> bool:
        return not self.unavailable

    async def decide(self, *, identity, auth_method, action, resource=None) -> AdminDecision:
        self.decide_calls.append({"principal": identity.principal, "action": action})
        if self.unavailable:
            raise PolicyUnavailable("down")
        allow = action not in self.deny_actions
        return AdminDecision(
            allow=allow,
            reason="allowed" if allow else "forbidden",
            package="opencg.admin",
            revision="rev-test",
        )

    async def entitle(self, *, identity, auth_method, request, candidates) -> EntitlementResult:
        cands = list(candidates)
        self.entitle_calls.append({"principal": identity.principal, "candidates": cands})
        if self.unavailable or self.entitle_unavailable:
            raise PolicyUnavailable("down")
        decisions = {}
        for c in cands:
            denied = c["classification"] in self.deny_classifications
            decisions[c["entity_id"]] = Decision(
                allow=not denied, reason="classification_restricted" if denied else "allowed"
            )
        return EntitlementResult(
            decisions=decisions, package="opencg.entitlement", revision="rev-test"
        )


class _Conn:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    async def execute(self, sql: str, *args: Any) -> None:
        self.rows.append(args)


class _Acquire:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _Conn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeAuditPool:
    """Collects access_audit_log inserts (the args tuple of each)."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def acquire(self) -> _Acquire:
        return _Acquire(_Conn(self.rows))

    def actions(self) -> list[tuple[str, str, str]]:
        # (principal, action, decision)
        return [(r[2], r[6], r[8]) for r in self.rows]


def install(app, *, opa: FakeOpa | None = None, auth: Authenticator | None = None) -> None:
    """Put an authenticator, OPA and an access-audit pool on `app.state`."""
    app.state.authenticator = auth or authenticator()
    app.state.opa = opa or FakeOpa()
    app.state.audit_pool = FakeAuditPool()
