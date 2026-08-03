"""Stable structured query input for memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..identifiers import require_memory_id
from ._validation import (
    coerce_enum,
    optional_aware_datetime,
    optional_text,
    require_tuple,
    require_token,
    require_unique_text_tuple,
)
from .memory import MemoryStatus
from .scope import MemoryScope


@dataclass(frozen=True)
class MemoryQuery:
    text: str | None = None
    memory_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    scope: MemoryScope | None = None
    statuses: tuple[MemoryStatus, ...] = (MemoryStatus.ACTIVE,)
    valid_at: datetime | None = None
    relation_types: tuple[str, ...] = ()
    include_related: bool = False
    limit: int = 50

    def __post_init__(self) -> None:
        optional_text(self.text, "text")
        memory_ids = require_tuple(self.memory_ids, "memory_ids")
        for memory_id in memory_ids:
            require_memory_id(memory_id, field="memory_ids item")
        if len(set(memory_ids)) != len(memory_ids):
            raise ValueError("memory_ids must not contain duplicates")
        require_unique_text_tuple(self.tags, "tags")
        if self.scope is not None and not isinstance(self.scope, MemoryScope):
            raise ValueError("scope must be a MemoryScope or None")

        statuses = require_tuple(self.statuses, "statuses")
        if not statuses:
            raise ValueError("statuses must contain at least one status")
        coerced_statuses = tuple(
            coerce_enum(item, MemoryStatus, "statuses item") for item in statuses
        )
        if len(set(coerced_statuses)) != len(coerced_statuses):
            raise ValueError("statuses must not contain duplicates")
        object.__setattr__(self, "statuses", coerced_statuses)

        optional_aware_datetime(self.valid_at, "valid_at")
        relation_types = require_unique_text_tuple(
            self.relation_types, "relation_types"
        )
        for relation_type in relation_types:
            require_token(relation_type, "relation_types item")
        if not isinstance(self.include_related, bool):
            raise ValueError("include_related must be a boolean")
        if relation_types and not self.include_related:
            raise ValueError(
                "relation_types requires include_related=True"
            )
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise ValueError("limit must be an integer")
        if not 1 <= self.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
