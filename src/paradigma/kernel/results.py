"""Explainable result values returned by memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .identifiers import require_memory_id
from .models._validation import require_unique_text_tuple
from .models.memory import MemoryRecord


@dataclass(frozen=True)
class MemoryResult:
    record: MemoryRecord
    score: float | None = None
    matched_fields: tuple[str, ...] = ()
    match_reasons: tuple[str, ...] = ()
    relation_source_id: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.record, MemoryRecord):
            raise ValueError("record must be a MemoryRecord")
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
                raise ValueError("score must be a finite non-negative number")
            if not math.isfinite(self.score) or self.score < 0:
                raise ValueError("score must be a finite non-negative number")
        require_unique_text_tuple(self.matched_fields, "matched_fields")
        require_unique_text_tuple(self.match_reasons, "match_reasons")
        require_unique_text_tuple(self.warnings, "warnings")
        if self.relation_source_id is not None:
            require_memory_id(
                self.relation_source_id, field="relation_source_id"
            )
            if self.relation_source_id == self.record.memory_id:
                raise ValueError("relation_source_id must identify another memory")
