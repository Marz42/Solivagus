"""Directed relations between memory records."""

from __future__ import annotations

from dataclasses import dataclass

from ..identifiers import require_memory_id
from ._validation import require_token


@dataclass(frozen=True)
class MemoryRelation:
    relation_type: str
    target_memory_id: str

    def __post_init__(self) -> None:
        require_token(self.relation_type, "relation_type")
        require_memory_id(self.target_memory_id, field="target_memory_id")
