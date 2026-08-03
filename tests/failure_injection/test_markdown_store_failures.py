from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.errors import AtomicWriteFailure
from paradigma.kernel import (
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.storage.errors import MemoryConflictError
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def record(*, revision: int = 1, content: str = "original") -> MemoryRecord:
    return MemoryRecord(
        memory_id=generate_memory_id(NOW, randomness=b"\x01" * 10),
        memory_type=MemoryType.SEMANTIC,
        title="Failure injection",
        content=content,
        scope=MemoryScope(namespace="test"),
        provenance=(
            ProvenanceRef(
                source_type=ProvenanceType.TOOL_RESULT,
                source_id="failure-test",
            ),
        ),
        status=MemoryStatus.ACTIVE,
        revision=revision,
        valid_from=None,
        valid_until=None,
        confidence=1.0,
        sensitivity="internal",
        tags=("failure",),
        relations=(),
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=revision - 1),
    )


class MarkdownStoreFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "memories"
        self.store = MarkdownMemoryStore(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_replace_failure_preserves_previous_revision_and_cleans_artifacts(self) -> None:
        created = self.store.create(record())
        before = created.path.read_bytes()

        with mock.patch(
            "paradigma.atomic.os.replace", side_effect=OSError("injected")
        ):
            with self.assertRaises(AtomicWriteFailure):
                self.store.update(
                    record(revision=2, content="new"),
                    expected_source_hash=created.source_hash,
                )

        self.assertEqual(before, created.path.read_bytes())
        self.assertEqual((), tuple(self.root.glob("*.tmp")))
        self.assertEqual((), tuple(self.root.glob("*.lock")))

    def test_create_publication_failure_leaves_no_document_or_temp_file(self) -> None:
        item = record()
        with mock.patch("paradigma.atomic.os.link", side_effect=OSError("injected")):
            with self.assertRaises(AtomicWriteFailure):
                self.store.create(item)

        self.assertFalse(self.store.path_for(item.memory_id).exists())
        self.assertEqual((), tuple(self.root.glob("*.tmp")))

    def test_existing_update_lock_refuses_second_writer_without_mutation(self) -> None:
        created = self.store.create(record())
        before = created.path.read_bytes()
        lock = self.root / f".{created.path.name}.lock"
        lock.write_text("held", encoding="utf-8")

        with self.assertRaisesRegex(MemoryConflictError, "already being updated"):
            self.store.update(
                replace(created.record, revision=2),
                expected_source_hash=created.source_hash,
            )
        self.assertEqual(before, created.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
