"""Anthropic model pricing (USD per million tokens).

Used as a fallback when authoritative cost figures aren't recorded
(orchestrator_events.payload_json `cost_usd`/`total_cost_usd` are empty
until Wave 3 wires them through). The resulting figures are *estimates* —
real billing may differ when Anthropic changes prices, applies discounts,
or when cache pricing tiers (5min vs 1hr) differ from the defaults below.

Source: anthropic.com/pricing (verified 2026-Q2). Update the table when
prices change.

Cache tokens use Anthropic's standard prompt-caching ratios:
  - cache_read_tokens are billed at 0.1× input price
  - cache_creation_tokens are billed at 1.25× input price (5-minute TTL)
"""
from __future__ import annotations
from collections.abc import Iterable, Mapping


# (input $/M, output $/M)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    # Claude 4.x family
    "opus-4":   (15.0, 75.0),
    "sonnet-4": (3.0, 15.0),
    "haiku-4":  (1.0, 5.0),
    # Claude 3.x family (still seen in older session logs)
    "opus-3":   (15.0, 75.0),
    "sonnet-3": (3.0, 15.0),
    "haiku-3-5": (0.80, 4.0),
    "haiku-3":  (0.25, 1.25),
}

CACHE_READ_FACTOR = 0.10
CACHE_WRITE_FACTOR = 1.25


def _match_prices(model: str | None) -> tuple[float, float]:
    """Find prices for a model string. Matching is by substring against the
    keys of MODEL_PRICES, preferring the *longest* key match (so `haiku-3-5`
    wins over `haiku-3` for `claude-haiku-3-5`). Unknown models return (0, 0)."""
    if not model:
        return (0.0, 0.0)
    m = model.lower()
    best: tuple[float, float] = (0.0, 0.0)
    best_len = 0
    for key, prices in MODEL_PRICES.items():
        if key in m and len(key) > best_len:
            best = prices
            best_len = len(key)
    return best


def cost_for(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Return USD cost estimate for a single model/usage tuple.

    Returns 0.0 for unknown models — caller can detect this by checking
    whether the model matched (or just accept that the figure is incomplete).
    """
    p_in, p_out = _match_prices(model)
    if p_in == 0 and p_out == 0:
        return 0.0
    return (
        input_tokens * p_in
        + output_tokens * p_out
        + cache_read_tokens * p_in * CACHE_READ_FACTOR
        + cache_creation_tokens * p_in * CACHE_WRITE_FACTOR
    ) / 1_000_000


def cost_for_groups(rows: Iterable[Mapping]) -> float:
    """Sum cost_for(...) over rows grouped by model.

    Each row must be a mapping with `model`, `input_tokens`, `output_tokens`,
    and (optionally) `cache_read_tokens`, `cache_creation_tokens` keys."""
    total = 0.0
    for r in rows:
        total += cost_for(
            r.get("model"),
            int(r.get("input_tokens") or 0),
            int(r.get("output_tokens") or 0),
            int(r.get("cache_read_tokens") or 0),
            int(r.get("cache_creation_tokens") or 0),
        )
    return total
