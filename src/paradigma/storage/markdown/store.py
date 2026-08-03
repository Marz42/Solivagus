"""Atomic filesystem store for canonical Markdown memory documents."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from paradigma.atomic import atomic_create_text, atomic_replace_text
from paradigma.kernel.identifiers import is_memory_id, require_memory_id
from paradigma.kernel.models.memory import MemoryRecord
from paradigma.parser import read_utf8_source
from paradigma.storage.contract import StoredMemory
from paradigma.storage.errors import (
    MemoryConflictError,
    MemoryDocumentError,
    MemoryNotFoundError,
    MemoryStorageError,
)

from .codec import MemoryMarkdownCodec


class MarkdownMemoryStore:
    def __init__(self, root: Path, *, codec: MemoryMarkdownCodec | None = None):
        self.root = Path(root).resolve()
        self.codec = codec or MemoryMarkdownCodec()

    def path_for(self, memory_id: str) -> Path:
        checked = require_memory_id(memory_id)
        return self.root / f"{checked}.md"

    def read(self, memory_id: str) -> StoredMemory:
        path = self.path_for(memory_id)
        if not path.exists():
            raise MemoryNotFoundError(path)
        if path.is_symlink():
            raise MemoryStorageError(f"memory document must not be a symlink: {path}")
        source = read_utf8_source(path)
        decoded = self.codec.inspect(source.text, source=str(path))
        if decoded.record.memory_id != memory_id:
            raise MemoryDocumentError(
                "memory_id does not match the canonical document filename"
            )
        return StoredMemory(
            record=decoded.record,
            content_hash=decoded.content_hash,
            source_hash=self.codec.source_hash_bytes(source.raw),
            path=path,
            canonical=(
                decoded.canonical
                and source.raw == source.text.encode("utf-8")
            ),
        )

    def create(self, record: MemoryRecord) -> StoredMemory:
        if record.revision != 1:
            raise MemoryConflictError("new memory documents must start at revision 1")
        path = self.path_for(record.memory_id)
        self.root.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise MemoryStorageError(f"memory document must not be a symlink: {path}")
        try:
            atomic_create_text(path, self.codec.encode(record))
        except FileExistsError as error:
            raise MemoryConflictError(
                f"memory document already exists: {path}"
            ) from error
        return self.read(record.memory_id)

    def update(
        self, record: MemoryRecord, *, expected_source_hash: str
    ) -> StoredMemory:
        self._require_source_hash(expected_source_hash)
        path = self.path_for(record.memory_id)
        with self._exclusive_update(path):
            current = self.read(record.memory_id)
            if current.source_hash != expected_source_hash:
                raise MemoryConflictError(
                    "memory document changed since it was read; refusing overwrite"
                )
            if record.revision != current.record.revision + 1:
                raise MemoryConflictError(
                    "updated memory revision must increment the stored revision by 1"
                )
            if record.created_at != current.record.created_at:
                raise MemoryConflictError(
                    "updated memory must preserve the original created_at"
                )
            if record.updated_at < current.record.updated_at:
                raise MemoryConflictError(
                    "updated_at must not be before the stored revision"
                )
            atomic_replace_text(path, self.codec.encode(record))
        return self.read(record.memory_id)

    def paths(self) -> tuple[Path, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            path
            for path in sorted(self.root.glob("MEM-*.md"), key=lambda item: item.name)
            if is_memory_id(path.stem) and path.is_file() and not path.is_symlink()
        )

    @contextmanager
    def _exclusive_update(self, path: Path) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f".{path.name}.lock"
        try:
            atomic_create_text(lock_path, f"target: {path.name}\n")
        except FileExistsError as error:
            raise MemoryConflictError(
                f"memory document is already being updated: {path}"
            ) from error
        try:
            yield
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError as error:
                raise MemoryStorageError(
                    f"failed to remove memory update lock {lock_path}: {error}"
                ) from error

    @staticmethod
    def _require_source_hash(value: str) -> None:
        if (
            not isinstance(value, str)
            or not value.startswith("sha256:")
            or len(value) != 71
            or any(character not in "0123456789abcdef" for character in value[7:])
        ):
            raise MemoryConflictError(
                "expected_source_hash must be a canonical sha256 digest"
            )
