from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.kernel import (
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.storage.catalog import CatalogQuery, CatalogQueryFailure
from paradigma.storage.catalog.sqlite import CatalogWriteFailure, SQLiteMemoryCatalog
from paradigma.storage.markdown import MarkdownMemoryStore
from paradigma.application.mutations import MemoryCatalogRefreshError, propose_memory
from paradigma.application.memory import explain_memory


NOW = datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc)


def record() -> MemoryRecord:
    return MemoryRecord(
        memory_id=generate_memory_id(NOW, randomness=b"\x03" * 10),
        memory_type=MemoryType.SEMANTIC,
        title="Catalog failure",
        content="Canonical content.",
        scope=MemoryScope(namespace="test"),
        provenance=(
            ProvenanceRef(
                source_type=ProvenanceType.TOOL_RESULT,
                source_id="catalog-failure",
            ),
        ),
        status=MemoryStatus.ACTIVE,
        revision=1,
        valid_from=None,
        valid_until=None,
        confidence=1.0,
        sensitivity="internal",
        tags=(),
        relations=(),
        created_at=NOW,
        updated_at=NOW,
    )


class SQLiteCatalogFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MarkdownMemoryStore(self.root / "memories")
        self.path = self.root / "cache" / "catalog.sqlite3"
        self.catalog = SQLiteMemoryCatalog(
            self.path, self.store, path_base=self.root
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_replace_failure_preserves_previous_catalog_and_cleans_temp_files(self) -> None:
        self.store.create(record())
        self.catalog.rebuild()
        before = self.path.read_bytes()

        with mock.patch(
            "paradigma.storage.catalog.sqlite.os.replace",
            side_effect=OSError("injected"),
        ):
            with self.assertRaises(CatalogWriteFailure):
                self.catalog.rebuild()

        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual((), tuple(self.path.parent.glob(".catalog.sqlite3.*.tmp")))

    def test_corrupt_database_is_reported_without_touching_markdown(self) -> None:
        stored = self.store.create(record())
        before = stored.path.read_bytes()
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"not a sqlite database")

        verification = self.catalog.verify()
        self.assertFalse(verification.current)
        self.assertTrue(any("cannot be read" in issue for issue in verification.issues))
        self.assertEqual(before, stored.path.read_bytes())

    def test_query_rejects_corrupt_database_without_touching_markdown(self) -> None:
        stored = self.store.create(record())
        before = stored.path.read_bytes()
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"not a sqlite database")

        with self.assertRaisesRegex(CatalogQueryFailure, "rebuilt"):
            self.catalog.query(
                CatalogQuery(MemoryQuery(memory_ids=(stored.record.memory_id,)))
            )

        self.assertEqual(before, stored.path.read_bytes())

    def test_catalog_refresh_failure_keeps_committed_canonical_candidate(self) -> None:
        config = self.root / ".paradigma" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: memory-bank/memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        proposal = {
            "memory_type": "semantic",
            "title": "Recoverable candidate",
            "content": "Canonical mutation survives catalog failure.",
            "scope": {"namespace": "test"},
            "provenance": [
                {"source_type": "tool_result", "source_id": "failure-test"}
            ],
        }
        identifier = record().memory_id
        with mock.patch(
            "paradigma.application.mutations.SQLiteMemoryCatalog.rebuild",
            side_effect=OSError("injected refresh failure"),
        ):
            with self.assertRaisesRegex(
                MemoryCatalogRefreshError, "canonical memory mutation succeeded"
            ):
                propose_memory(
                    self.root,
                    proposal,
                    memory_id=identifier,
                    at=NOW,
                    write=True,
                )

        stored = MarkdownMemoryStore(
            self.root / "memory-bank" / "memories"
        ).read(identifier)
        self.assertEqual("candidate", stored.record.status.value)
        self.assertEqual(1, stored.record.revision)

    def test_explain_survives_corrupt_catalog_without_touching_canonical(self) -> None:
        config = self.root / ".paradigma" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        stored = self.store.create(record())
        before = stored.path.read_bytes()
        catalog = self.root / ".paradigma" / "cache" / "catalog.sqlite3"
        catalog.parent.mkdir(parents=True)
        catalog.write_bytes(b"not a sqlite database")

        explanation = explain_memory(self.root, stored.record.memory_id, at=NOW)

        self.assertFalse(explanation.catalog_current)
        self.assertTrue(any("catalog" in item for item in explanation.warnings))
        self.assertEqual(before, stored.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
