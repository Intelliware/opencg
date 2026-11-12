"""Cost estimation from the `observability.pricing` table in opencg.yaml.

Prices are USD per 1,000 tokens, keyed by (provider, model). A pair with no
entry is *unpriced*: its cost is `None`, never zero, so gaps stay visible.

The table is loaded lazily from `load_config()` on first use, so every
process (long-lived servers and one-shot CLI runs alike) prices the same way
without extra wiring. Services may call `configure()` at start-up to load an
explicit table instead.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

from opencg_shared.config import PriceEntry, load_config

log = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict[str, dict[tuple[str, str], PriceEntry] | None] = {"table": None}
_warned: set[tuple[str, str]] = set()

COST_DECIMALS = 6


def configure(entries: Iterable[PriceEntry]) -> None:
    """Replace the price table (call at start-up, or from tests)."""
    with _lock:
        _state["table"] = {(e.provider, e.model): e for e in entries}
        _warned.clear()


def reset() -> None:
    """Forget the table so the next lookup reloads it from config."""
    with _lock:
        _state["table"] = None
        _warned.clear()


def _get_table() -> dict[tuple[str, str], PriceEntry]:
    if _state["table"] is None:
        try:
            entries = load_config().observability.pricing
        except Exception as exc:  # pragma: no cover - config errors surface elsewhere
            log.warning("could not load the price table: %s", exc)
            entries = []
        configure(entries)
    table = _state["table"]
    assert table is not None
    return table


def price_for(provider: str | None, model: str | None) -> PriceEntry | None:
    if not provider or not model:
        return None
    return _get_table().get((provider, model))


def cost_usd(
    provider: str | None,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
) -> float | None:
    """Estimated cost in USD, or `None` when the pair has no price entry."""
    entry = price_for(provider, model)
    if entry is None:
        key = (provider or "n/a", model or "n/a")
        if key not in _warned:
            _warned.add(key)
            log.warning(
                "no price entry for provider=%s model=%s; its tokens are counted as unpriced",
                key[0],
                key[1],
            )
        return None
    cost = tokens_in / 1000 * entry.input_usd_per_1k + tokens_out / 1000 * entry.output_usd_per_1k
    return round(cost, COST_DECIMALS)
