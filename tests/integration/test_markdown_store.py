from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.kernel import (
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.storage.errors import (
    MemoryConflictError,
    MemoryIntegrityError,
    MemoryNotFoundError,
)
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)


def memory_id(seed: int = 1) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def record(**overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(),
        "memory_type": MemoryType.SEMANTIC,
        "title": "Canonical memory",
        "content": "A durable Markdown record.",
        "scope": MemoryScope(namespace="test", project_id="project-1"),
        "provenance": (
            ProvenanceRef(
                source_type=ProvenanceType.MANUAL_ENTRY,
                source_id="entry-1",
                observed_at=NOW,
                actor="tester",
            ),
        ),
        "status": MemoryStatus.ACTIVE,
        "revision": 1,
        "valid_from": None,
        "valid_until": None,
        "confidence": 1.0,
        "sensitivity": "internal",
        "tags": ("store",),
        "relations": (),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


class MarkdownMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "memories"
        self.store = MarkdownMemoryStore(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_read_update_round_trip_and_revision_contract(self) -> None:
        original = record()
        created = self.store.create(original)

        self.assertEqual(original, created.record)
        self.assertEqual(
            (self.root / f"{original.memory_id}.md").resolve(),
            created.path.resolve(),
        )
        self.assertTrue(created.canonical)
        self.assertEqual(created, self.store.read(original.memory_id))

        revised = replace(
            original,
            content="Revision two.",
            revision=2,
            updated_at=NOW + timedelta(seconds=1),
        )
        updated = self.store.update(
            revised, expected_source_hash=created.source_hash
        )
        self.assertEqual(revised, updated.record)
        self.assertNotEqual(created.source_hash, updated.source_hash)
        self.assertFalse(
            any(path.name.endswith(".tmp") for path in self.root.iterdir())
        )
        self.assertFalse(any(path.name.endswith(".lock") for path in self.root.iterdir()))

    def test_create_and_update_refuse_revision_errors(self) -> None:
        with self.assertRaisesRegex(MemoryConflictError, "revision 1"):
            self.store.create(record(revision=2))

        created = self.store.create(record())
        with self.assertRaisesRegex(MemoryConflictError, "increment"):
            self.store.update(
                replace(created.record, revision=3),
                expected_source_hash=created.source_hash,
            )
        with self.assertRaisesRegex(MemoryConflictError, "already exists"):
            self.store.create(record())

    def test_source_hash_detects_format_only_manual_edit(self) -> None:
        created = self.store.create(record())
        path = created.path
        original = path.read_text(encoding="utf-8")
        path.write_bytes(b"\xef\xbb\xbf" + original.encode("utf-8"))

        edited = self.store.read(created.record.memory_id)
        self.assertEqual(created.record, edited.record)
        self.assertFalse(edited.canonical)
        self.assertNotEqual(created.source_hash, edited.source_hash)
        with self.assertRaisesRegex(MemoryConflictError, "changed since"):
            self.store.update(
                replace(created.record, revision=2),
                expected_source_hash=created.source_hash,
            )

    def test_unhashed_manual_content_edit_fails_integrity_check(self) -> None:
        created = self.store.create(record())
        text = created.path.read_text(encoding="utf-8")
        created.path.write_text(
            text.replace("A durable Markdown record.", "A manual edit."),
            encoding="utf-8",
        )
        with self.assertRaises(MemoryIntegrityError):
            self.store.read(created.record.memory_id)

    def test_paths_are_sorted_and_ignore_unmanaged_files(self) -> None:
        second = self.store.create(record(memory_id=memory_id(2)))
        first = self.store.create(record(memory_id=memory_id(1)))
        (self.root / "notes.md").write_text("not managed", encoding="utf-8")

        self.assertEqual((first.path, second.path), self.store.paths())

    def test_missing_memory_has_stable_error(self) -> None:
        with self.assertRaises(MemoryNotFoundError) as raised:
            self.store.read(memory_id())
        self.assertEqual("PD_MEMORY_NOT_FOUND", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
