"""Canonical memory record and lifecycle enums."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math

from ..identifiers import require_memory_id
from ._validation import (
    coerce_enum,
    require_aware_datetime,
    require_text,
    require_tuple,
    require_unique_text_tuple,
)
from .provenance import ProvenanceRef, ProvenanceType
from .relation import MemoryRelation
from .scope import MemoryScope


class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    DECISION = "decision"
    WORKING = "working"


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"
    TOMBSTONED = "tombstoned"


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    memory_type: MemoryType
    title: str
    content: str
    scope: MemoryScope
    provenance: tuple[ProvenanceRef, ...]
    status: MemoryStatus
    revision: int
    valid_from: datetime | None
    valid_until: datetime | None
    confidence: float | None
    sensitivity: str
    tags: tuple[str, ...]
    relations: tuple[MemoryRelation, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_memory_id(self.memory_id)
        memory_type = coerce_enum(self.memory_type, MemoryType, "memory_type")
        status = coerce_enum(self.status, MemoryStatus, "status")
        object.__setattr__(self, "memory_type", memory_type)
        object.__setattr__(self, "status", status)
        require_text(self.title, "title")
        require_text(self.content, "content")
        require_text(self.sensitivity, "sensitivity")
        if not isinstance(self.scope, MemoryScope):
            raise ValueError("scope must be a MemoryScope")

        provenance = require_tuple(self.provenance, "provenance")
        if not provenance:
            raise ValueError("provenance must contain at least one source")
        if not all(isinstance(item, ProvenanceRef) for item in provenance):
            raise ValueError("provenance must contain only ProvenanceRef values")
        if len(set(provenance)) != len(provenance):
            raise ValueError("provenance must not contain duplicates")

        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise ValueError("revision must be an integer")
        if self.revision < 1:
            raise ValueError("revision must be at least 1")

        created_at = require_aware_datetime(self.created_at, "created_at")
        updated_at = require_aware_datetime(self.updated_at, "updated_at")
        valid_from = self._optional_instant(self.valid_from, "valid_from")
        valid_until = self._optional_instant(self.valid_until, "valid_until")
        if updated_at < created_at:
            raise ValueError("updated_at must not be before created_at")
        if valid_from is not None and valid_until is not None:
            if valid_until < valid_from:
                raise ValueError("valid_until must not be before valid_from")

        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(
                self.confidence, (int, float)
            ):
                raise ValueError("confidence must be a number between 0 and 1")
            if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
                raise ValueError("confidence must be a number between 0 and 1")
        if any(
            item.source_type is ProvenanceType.AGENT_INFERENCE
            for item in provenance
        ) and self.confidence is None:
            raise ValueError("agent_inference provenance requires confidence")

        require_unique_text_tuple(self.tags, "tags")
        relations = require_tuple(self.relations, "relations")
        if not all(isinstance(item, MemoryRelation) for item in relations):
            raise ValueError("relations must contain only MemoryRelation values")
        if len(set(relations)) != len(relations):
            raise ValueError("relations must not contain duplicates")
        if any(item.target_memory_id == self.memory_id for item in relations):
            raise ValueError("a memory record cannot relate to itself")

    @staticmethod
    def _optional_instant(value: object, field: str) -> datetime | None:
        if value is None:
            return None
        return require_aware_datetime(value, field)

    def is_valid_at(self, instant: datetime) -> bool:
        """Return whether the record's inclusive validity interval contains instant."""

        checked = require_aware_datetime(instant, "instant")
        if self.valid_from is not None and checked < self.valid_from:
            return False
        if self.valid_until is not None and checked > self.valid_until:
            return False
        return True
