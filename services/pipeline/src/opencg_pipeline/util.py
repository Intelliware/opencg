"""Shared helpers (token estimation, hashing)."""

from __future__ import annotations

import hashlib
import math


def estimate_tokens(text: str, *, tokens_per_char: float = 0.25) -> int:
    """Rough token count when no real tokenizer is wired in."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) * tokens_per_char))


def reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int = 60) -> dict[str, float]:
    """RRF fusion: combine multiple ranked lists into a single score map."""
    scores: dict[str, float] = {}
    for ranking in ranked_lists:
        for rank, eid in enumerate(ranking):
            scores[eid] = scores.get(eid, 0.0) + 1.0 / (k + rank + 1)
    return scores


def hash_context(fragments: list[dict]) -> str:
    """Deterministic hash of an ordered fragment list — feeds final_context_hash."""
    h = hashlib.sha256()
    for f in fragments:
        h.update(f["entity_id"].encode())
        h.update(b"\0")
        h.update(str(f.get("score", 0.0)).encode())
        h.update(b"\0")
        h.update(f.get("text", "").encode())
        h.update(b"\x1e")
    return h.hexdigest()
