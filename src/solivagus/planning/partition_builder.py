"""Pack translation units into cache partitions."""

from __future__ import annotations

from dataclasses import dataclass

from solivagus.planning.unit_builder import PlannedUnit


@dataclass
class PartitionBudget:
    first_target_tokens: int = 96_000
    target_tokens: int = 220_000
    max_tokens: int = 300_000


@dataclass
class PlannedPartition:
    sequence_index: int
    unit_keys: list[str]
    source_tokens: int
    unit_count: int
    status: str = "pending"


def build_cache_partitions(
    units: list[PlannedUnit],
    *,
    budget: PartitionBudget | None = None,
) -> list[PlannedPartition]:
    budget = budget or PartitionBudget()
    if not units:
        return []

    partitions: list[PlannedPartition] = []
    current_keys: list[str] = []
    current_tokens = 0

    def target_for_index(index: int) -> int:
        return budget.first_target_tokens if index == 1 else budget.target_tokens

    def flush() -> None:
        nonlocal current_keys, current_tokens
        if not current_keys:
            return
        index = len(partitions) + 1
        partitions.append(
            PlannedPartition(
                sequence_index=index,
                unit_keys=list(current_keys),
                source_tokens=current_tokens,
                unit_count=len(current_keys),
            )
        )
        current_keys = []
        current_tokens = 0

    for unit in units:
        next_index = len(partitions) + 1
        target = target_for_index(next_index)
        tokens = unit.source_tokens
        if current_keys and current_tokens + tokens > target:
            # Allow growth up to max before forcing a new partition.
            if current_tokens + tokens <= budget.max_tokens and current_tokens < target:
                pass
            else:
                flush()
                next_index = len(partitions) + 1
                target = target_for_index(next_index)

        if current_keys and current_tokens + tokens > budget.max_tokens:
            flush()

        current_keys.append(unit.unit_key)
        current_tokens += tokens

        # Close when we reach/exceed the soft target.
        next_index = len(partitions) + 1
        if current_tokens >= target_for_index(next_index):
            flush()

    flush()
    return partitions
