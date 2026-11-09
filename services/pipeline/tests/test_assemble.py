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
    kept, decisions = run(
        candidates=cands, roles=["reader"], token_budget=2500, tokens_per_char=0.25
    )
    assert len(kept) == 2
    drops = [d for d in decisions if d["decision"] == "drop"]
    assert len(drops) == 3
    assert all(d["reason"] == "budget_exhausted" for d in drops)


def test_classification_filtered():
    cands = [
        _c("e1", "ok", classification="public"),
        _c("e2", "secret", classification="confidential:legal"),
    ]
    kept, decisions = run(
        candidates=cands, roles=["reader"], token_budget=1000, tokens_per_char=0.25
    )
    assert [c.entity_id for c in kept] == ["e1"]
    deny = [d for d in decisions if d["decision"] == "deny"]
    assert deny[0]["entity_id"] == "e2"
    assert deny[0]["reason"] == "classification_restricted"


def test_empty_input():
    kept, decisions = run(candidates=[], roles=["reader"], token_budget=1000, tokens_per_char=0.25)
    assert kept == []
    assert decisions == []
