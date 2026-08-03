"""Stable failures raised by canonical memory storage."""

from __future__ import annotations

from pathlib import Path

from paradigma.errors import ParadigmaError


class MemoryStorageError(ParadigmaError):
    code = "PD_MEMORY_STORAGE_ERROR"
    exit_code = 2


class MemoryDocumentError(MemoryStorageError, ValueError):
    code = "PD_MEMORY_SCHEMA_ERROR"


class MemoryIntegrityError(MemoryDocumentError):
    code = "PD_MEMORY_INTEGRITY_ERROR"


class MemoryConflictError(MemoryStorageError):
    code = "PD_MEMORY_CONFLICT"
    exit_code = 3


class MemoryNotFoundError(MemoryStorageError, FileNotFoundError):
    code = "PD_MEMORY_NOT_FOUND"

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"memory document does not exist: {path}")
