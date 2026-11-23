"""Policy decisions from OPA (add-identity-and-opa, design D7, D8, D9, D10).

- `entitle()`: one batched call per retrieval, a decision per candidate.
- `decide()`: one call per admin action.
Both fail closed: OPA unreachable, slow (`OPENCG__OPA__TIMEOUT_MS`, default 2 s),
non-2xx, or a malformed/partial answer raises `PolicyUnavailable`.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from opencg_shared.types import IdentityContext

log = logging.getLogger(__name__)

ENTITLEMENT_PATH = "/v1/data/opencg/entitlement/decisions"
ADMIN_PATH = "/v1/data/opencg/admin/decision"


# Classifications the default policy understands (design D7).
CLASSIFICATION_RE = re.compile(r"^(public|internal|confidential:[a-z0-9-]+)$")


def is_valid_classification(value: str) -> bool:
    return bool(CLASSIFICATION_RE.match(value))


class PolicyUnavailable(Exception):
    """OPA could not give a usable decision; callers must fail closed."""


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


@dataclass(frozen=True)
class EntitlementResult:
    decisions: dict[str, Decision]
    package: str
    revision: str


@dataclass(frozen=True)
class AdminDecision:
    allow: bool
    reason: str
    package: str
    revision: str


def principal_input(identity: IdentityContext, auth_method: str) -> dict[str, Any]:
    return {
        "id": identity.principal,
        "roles": list(identity.roles),
        "tenant": identity.tenant,
        "auth_method": auth_method,
    }


class OpaClient:
    def __init__(
        self,
        url: str | None = None,
        *,
        timeout_ms: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = (url or os.environ.get("OPENCG__OPA__URL") or "http://opa:8181").rstrip("/")
        timeout = timeout_ms or int(os.environ.get("OPENCG__OPA__TIMEOUT_MS") or 2000)
        self._client = client or httpx.AsyncClient(timeout=timeout / 1000)

    async def close(self) -> None:
        await self._client.aclose()

    async def _query(self, path: str, payload: dict[str, Any]) -> Mapping[str, Any]:
        try:
            resp = await self._client.post(f"{self.url}{path}", json={"input": payload})
        except httpx.HTTPError as exc:
            raise PolicyUnavailable(f"OPA unreachable: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise PolicyUnavailable(f"OPA returned HTTP {resp.status_code}")
        try:
            result = resp.json().get("result")
        except ValueError as exc:
            raise PolicyUnavailable("OPA returned invalid JSON") from exc
        if not isinstance(result, Mapping):
            raise PolicyUnavailable("OPA returned no result (policy not loaded?)")
        return result

    async def ready(self) -> bool:
        try:
            resp = await self._client.get(f"{self.url}/health")
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    async def entitle(
        self,
        *,
        identity: IdentityContext,
        auth_method: str,
        request: Mapping[str, Any],
        candidates: Iterable[Mapping[str, Any]],
    ) -> EntitlementResult:
        cands = [dict(c) for c in candidates]
        result = await self._query(
            ENTITLEMENT_PATH,
            {
                "principal": principal_input(identity, auth_method),
                "request": dict(request),
                "candidates": cands,
            },
        )
        raw = result.get("decisions")
        if not isinstance(raw, Mapping):
            raise PolicyUnavailable("OPA entitlement result has no decisions")
        decisions: dict[str, Decision] = {}
        for cand in cands:
            entity_id = str(cand["entity_id"])
            d = raw.get(entity_id)
            if not isinstance(d, Mapping) or not isinstance(d.get("allow"), bool):
                raise PolicyUnavailable(f"OPA gave no decision for candidate {entity_id}")
            decisions[entity_id] = Decision(allow=d["allow"], reason=str(d.get("reason", "")))
        return EntitlementResult(
            decisions=decisions,
            package=str(result.get("package", "opencg.entitlement")),
            revision=str(result.get("revision", "")),
        )

    async def decide(
        self,
        *,
        identity: IdentityContext,
        auth_method: str,
        action: str,
        resource: str | None = None,
    ) -> AdminDecision:
        result = await self._query(
            ADMIN_PATH,
            {
                "principal": principal_input(identity, auth_method),
                "action": action,
                "resource": resource,
            },
        )
        if not isinstance(result.get("allow"), bool):
            raise PolicyUnavailable("OPA admin decision has no boolean 'allow'")
        return AdminDecision(
            allow=result["allow"],
            reason=str(result.get("reason", "")),
            package=str(result.get("package", "opencg.admin")),
            revision=str(result.get("revision", "")),
        )


def access_audit_row(
    *,
    correlation_id: str,
    service: str,
    identity: IdentityContext,
    auth_method: str,
    action: str,
    resource: str | None,
    decision: AdminDecision,
) -> dict[str, Any]:
    """A row for `opencg.access_audit_log`."""
    return {
        "correlation_id": correlation_id,
        "service": service,
        "principal": identity.principal,
        "roles": list(identity.roles),
        "tenant": identity.tenant,
        "auth_method": auth_method,
        "action": action,
        "resource": resource,
        "decision": "allow" if decision.allow else "deny",
        "reason": decision.reason,
        "policy_package": decision.package,
        "policy_revision": decision.revision,
    }
