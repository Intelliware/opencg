"""Stage 6 (thin MVP): token-budget assemble.

The thin MVP collapses Stage 5 (rerank+compress) and Stage 6 (entitle+audit)
into a single budget-enforced assemble. Entitlement is permissive (allow all
candidates whose classification is in the principal's allowed list).
"""

from __future__ import annotations

from opencg_pipeline.stages.hybrid_retrieval import Candidate
from opencg_pipeline.util import estimate_tokens

# Stub policy until OPA wires in. Roles map to classification allow-lists.
_ROLE_ALLOWED_CLASSIFICATIONS: dict[str, set[str]] = {
    "admin": {"internal", "public"},
    "reader": {"internal", "public"},
    "public": {"public"},
}


def _allowed_for(roles: list[str] | tuple[str, ...]) -> set[str]:
    allowed: set[str] = set()
    for role in roles:
        allowed |= _ROLE_ALLOWED_CLASSIFICATIONS.get(role, set())
    return allowed or {"public"}


def run(
    *,
    candidates: list[Candidate],
    roles: list[str] | tuple[str, ...],
    token_budget: int,
    tokens_per_char: float,
) -> tuple[list[Candidate], list[dict]]:
    """Return (kept, decisions).

    `decisions` records per-candidate policy + budget outcome for the audit log.
    """
    allowed = _allowed_for(list(roles))
    decisions: list[dict] = []
    kept: list[Candidate] = []
    used = 0
    for c in candidates:
        tokens = estimate_tokens(c.text, tokens_per_char=tokens_per_char)
        if c.classification not in allowed:
            decisions.append(
                {
                    "entity_id": c.entity_id,
                    "decision": "deny",
                    "reason": "classification_restricted",
                }
            )
            continue
        if used + tokens > token_budget:
            decisions.append(
                {"entity_id": c.entity_id, "decision": "drop", "reason": "budget_exhausted"}
            )
            continue
        kept.append(c)
        used += tokens
        decisions.append({"entity_id": c.entity_id, "decision": "include", "tokens": tokens})
    return kept, decisions
