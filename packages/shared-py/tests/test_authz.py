"""opencg_shared.authz: the OPA client fails closed."""

from __future__ import annotations

import httpx
import pytest
import respx
from opencg_shared.authz import OpaClient, PolicyUnavailable, access_audit_row
from opencg_shared.types import IdentityContext

pytestmark = pytest.mark.asyncio

OPA = "http://opa:8181"
ENT = f"{OPA}/v1/data/opencg/entitlement/decisions"
ADM = f"{OPA}/v1/data/opencg/admin/decision"
ALICE = IdentityContext(principal="alice", roles=("reader",), tenant="default")
CANDS = [
    {"entity_id": "e1", "classification": "internal", "source": "git", "source_uri": "u1"},
    {
        "entity_id": "e2",
        "classification": "confidential:legal",
        "source": "git",
        "source_uri": "u2",
    },
]


async def _entitle():
    client = OpaClient(OPA, timeout_ms=200)
    try:
        return await client.entitle(
            identity=ALICE, auth_method="oidc", request={"tool": "t"}, candidates=CANDS
        )
    finally:
        await client.close()


@respx.mock
async def test_entitlement_allow_and_deny():
    route = respx.post(ENT).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "decisions": {
                        "e1": {"allow": True, "reason": "allowed"},
                        "e2": {"allow": False, "reason": "classification_restricted"},
                    },
                    "package": "opencg.entitlement",
                    "revision": "abc",
                }
            },
        )
    )
    result = await _entitle()
    assert result.decisions["e1"].allow is True
    assert result.decisions["e2"].reason == "classification_restricted"
    assert result.revision == "abc"
    body = route.calls[0].request.read()
    assert b'"auth_method":"oidc"' in body.replace(b" ", b"")
    assert route.call_count == 1  # one batched call


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={}),  # policy not loaded: no result
        httpx.Response(200, json={"result": {"decisions": {"e1": {"allow": True}}}}),  # partial
        httpx.Response(200, json={"result": {"decisions": {"e1": {"allow": "yes"}, "e2": {}}}}),
    ],
)
@respx.mock
async def test_entitlement_fails_closed(response):
    respx.post(ENT).mock(return_value=response)
    with pytest.raises(PolicyUnavailable):
        await _entitle()


@respx.mock
async def test_entitlement_timeout_fails_closed():
    respx.post(ENT).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(PolicyUnavailable):
        await _entitle()


@respx.mock
async def test_admin_decision_and_audit_row():
    respx.post(ADM).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "allow": False,
                    "reason": "forbidden",
                    "package": "opencg.admin",
                    "revision": "r1",
                }
            },
        )
    )
    client = OpaClient(OPA)
    try:
        d = await client.decide(
            identity=ALICE, auth_method="oidc", action="entity.tombstone", resource="e1"
        )
    finally:
        await client.close()
    assert d.allow is False
    row = access_audit_row(
        correlation_id="c",
        service="pipeline",
        identity=ALICE,
        auth_method="oidc",
        action="entity.tombstone",
        resource="e1",
        decision=d,
    )
    assert row["decision"] == "deny"
    assert row["policy_revision"] == "r1"
    assert row["roles"] == ["reader"]


@respx.mock
async def test_admin_decision_malformed_fails_closed():
    respx.post(ADM).mock(return_value=httpx.Response(200, json={"result": {"reason": "x"}}))
    client = OpaClient(OPA)
    try:
        with pytest.raises(PolicyUnavailable):
            await client.decide(identity=ALICE, auth_method="none", action="graph.read")
    finally:
        await client.close()
