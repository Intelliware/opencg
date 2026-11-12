"""Stage 5: entitlement (add-identity-and-opa, design D8).

One batched OPA call per retrieval decides every candidate. Denied candidates
are removed here, before the token budget, and recorded with the policy package
and revision for the audit row. `PolicyUnavailable` propagates: callers fail
closed.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencg_shared import IdentityContext
from opencg_shared.authz import EntitlementResult, OpaClient

from opencg_pipeline.stages.hybrid_retrieval import Candidate


@dataclass(frozen=True)
class EntitleOutcome:
    allowed: list[Candidate]
    denied: list[dict]  # candidate_decisions entries for denied candidates
    result: EntitlementResult


async def run(
    *,
    opa: OpaClient,
    identity: IdentityContext,
    auth_method: str,
    tool: str,
    correlation_id: str,
    candidates: list[Candidate],
) -> EntitleOutcome:
    result = await opa.entitle(
        identity=identity,
        auth_method=auth_method,
        request={"tool": tool, "correlation_id": correlation_id},
        candidates=[
            {
                "entity_id": c.entity_id,
                "classification": c.classification,
                "source": c.source,
                "source_uri": c.source_uri,
            }
            for c in candidates
        ],
    )
    allowed: list[Candidate] = []
    denied: list[dict] = []
    for c in candidates:
        decision = result.decisions[c.entity_id]
        if decision.allow:
            allowed.append(c)
        else:
            denied.append(
                {
                    "entity_id": c.entity_id,
                    "decision": "deny",
                    "reason": decision.reason,
                    "policy_package": result.package,
                    "policy_revision": result.revision,
                }
            )
    return EntitleOutcome(allowed=allowed, denied=denied, result=result)
