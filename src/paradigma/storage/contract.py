"""Adapter-neutral contracts for canonical memory storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from paradigma.kernel.models.memory import MemoryRecord


@dataclass(frozen=True)
class StoredMemory:
    record: MemoryRecord
    content_hash: str
    source_hash: str
    path: Path
    canonical: bool


class MemoryStore(Protocol):
    def read(self, memory_id: str) -> StoredMemory: ...

    def create(self, record: MemoryRecord) -> StoredMemory: ...

    def update(
        self, record: MemoryRecord, *, expected_source_hash: str
    ) -> StoredMemory: ...
