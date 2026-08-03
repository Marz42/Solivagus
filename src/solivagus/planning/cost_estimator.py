"""Cost estimation for planned units/partitions (DeepSeek flash defaults)."""

from __future__ import annotations

from dataclasses import dataclass

from solivagus.planning.partition_builder import PlannedPartition
from solivagus.planning.unit_builder import PlannedUnit


@dataclass
class PriceProfile:
    cache_hit_per_million: float = 0.02
    cache_miss_per_million: float = 1.00
    output_per_million: float = 2.00
    currency: str = "CNY"


@dataclass
class CostEstimate:
    cache_miss_tokens: int
    cache_hit_tokens: int
    output_tokens: int
    estimated_cost: float
    currency: str
    mode: str


def estimate_cost(
    units: list[PlannedUnit],
    partitions: list[PlannedPartition],
    *,
    price: PriceProfile | None = None,
    mode: str = "approximate",
) -> CostEstimate:
    price = price or PriceProfile()
    unit_by_key = {u.unit_key: u for u in units}

    cache_miss = 0
    cache_hit = 0
    output = 0

    for part in partitions:
        part_units = [unit_by_key[k] for k in part.unit_keys if k in unit_by_key]
        if not part_units:
            continue
        # First unit in partition pays full source as cache miss (warm-up proxy).
        first = part_units[0].source_tokens
        rest = sum(u.source_tokens for u in part_units[1:])
        # Repeat-mode: each unit also re-sends its own source as the request tail.
        repeat_tail = sum(u.source_tokens for u in part_units)
        cache_miss += first + repeat_tail
        cache_hit += rest
        output += sum(u.estimated_output_tokens for u in part_units)

    cost = (
        cache_hit / 1_000_000 * price.cache_hit_per_million
        + cache_miss / 1_000_000 * price.cache_miss_per_million
        + output / 1_000_000 * price.output_per_million
    )
    return CostEstimate(
        cache_miss_tokens=cache_miss,
        cache_hit_tokens=cache_hit,
        output_tokens=output,
        estimated_cost=round(cost, 4),
        currency=price.currency,
        mode=mode,
    )
