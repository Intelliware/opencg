"""Stage 6: token-budget assemble.

Entitlement is no longer decided here: the entitle stage (stages/entitle.py)
asks OPA first and passes on only allowed candidates, so denied candidates never
use budget. This stage only enforces the token budget.
"""

from __future__ import annotations

from opencg_pipeline.stages.hybrid_retrieval import Candidate
from opencg_pipeline.util import estimate_tokens


def run(
    *,
    candidates: list[Candidate],
    token_budget: int,
    tokens_per_char: float,
) -> tuple[list[Candidate], list[dict]]:
    """Return (kept, decisions) for the allowed candidates, in score order."""
    decisions: list[dict] = []
    kept: list[Candidate] = []
    used = 0
    for c in candidates:
        tokens = estimate_tokens(c.text, tokens_per_char=tokens_per_char)
        if used + tokens > token_budget:
            decisions.append(
                {"entity_id": c.entity_id, "decision": "drop", "reason": "budget_exhausted"}
            )
            continue
        kept.append(c)
        used += tokens
        decisions.append({"entity_id": c.entity_id, "decision": "include", "tokens": tokens})
    return kept, decisions
