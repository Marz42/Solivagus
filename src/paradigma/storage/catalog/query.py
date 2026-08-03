"""Structured query values for the derived memory catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath

from paradigma.kernel import MemoryQuery


class CatalogTextMode(str, Enum):
    KEYWORD = "keyword"
    FTS = "fts"


@dataclass(frozen=True)
class CatalogQuery:
    """Storage-aware query wrapper around the domain-neutral MemoryQuery."""

    memory: MemoryQuery = field(default_factory=MemoryQuery)
    paths: tuple[str, ...] = ()
    text_mode: CatalogTextMode = CatalogTextMode.FTS

    def __post_init__(self) -> None:
        if not isinstance(self.memory, MemoryQuery):
            raise ValueError("memory must be a MemoryQuery")
        if not isinstance(self.paths, tuple):
            raise ValueError("paths must be a tuple")
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("paths must not contain duplicates")
        for path in self.paths:
            _require_catalog_path(path)
        try:
            mode = CatalogTextMode(self.text_mode)
        except (TypeError, ValueError) as error:
            raise ValueError("text_mode must be keyword or fts") from error
        object.__setattr__(self, "text_mode", mode)


def _require_catalog_path(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("catalog path must be a non-empty canonical string")
    if "\\" in value:
        raise ValueError("catalog path must use forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("catalog path must be repository-relative without traversal")
    if path.as_posix() != value:
        raise ValueError("catalog path must be canonical")
    return value
