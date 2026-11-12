from __future__ import annotations

from opencg_pipeline.stages.assemble import run
from opencg_pipeline.stages.hybrid_retrieval import Candidate


def _c(eid: str, text: str, classification: str = "internal", score: float = 1.0) -> Candidate:
    return Candidate(
        entity_id=eid,
        score=score,
        source="git",
        source_uri=f"file://{eid}",
        title=None,
        text=text,
        classification=classification,
        via=["dense"],
    )


def test_budget_enforced():
    cands = [_c(f"e{i}", "x" * 4000) for i in range(5)]  # ~1000 tokens each at 0.25 t/c
    kept, decisions = run(candidates=cands, token_budget=2500, tokens_per_char=0.25)
    assert len(kept) == 2
    drops = [d for d in decisions if d["decision"] == "drop"]
    assert len(drops) == 3
    assert all(d["reason"] == "budget_exhausted" for d in drops)


def test_assemble_has_no_classification_rules():
    """Entitlement is OPA's job (entitle stage); assemble keeps anything it is given."""
    cands = [_c("e1", "ok", classification="public"), _c("e2", "x", "confidential:legal")]
    kept, decisions = run(candidates=cands, token_budget=1000, tokens_per_char=0.25)
    assert [c.entity_id for c in kept] == ["e1", "e2"]
    assert all(d["decision"] == "include" for d in decisions)
