from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.kernel import (
    MemoryRecord,
    MemoryRelation,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.cli.main import main
from paradigma.storage.catalog import (
    CATALOG_SCHEMA_VERSION,
    CatalogFailure,
    SQLiteMemoryCatalog,
)
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc)


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def record(seed: int = 1, **overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(seed),
        "memory_type": MemoryType.SEMANTIC,
        "title": f"Catalog record {seed}",
        "content": f"# Heading\n\nSearchable body number {seed}.",
        "scope": MemoryScope(
            namespace="catalog-test",
            workspace_id="workspace-1",
            project_id="project-1",
            entity_ids=(f"entity-{seed}",),
        ),
        "provenance": (
            ProvenanceRef(
                source_type=ProvenanceType.TOOL_RESULT,
                source_id=f"tool-{seed}",
                observed_at=NOW,
                actor="test",
            ),
        ),
        "status": MemoryStatus.ACTIVE,
        "revision": 1,
        "valid_from": NOW,
        "valid_until": NOW + timedelta(days=seed),
        "confidence": 0.8,
        "sensitivity": "internal",
        "tags": ("catalog", f"number-{seed}"),
        "relations": (
            (MemoryRelation("related_to", memory_id(2)),) if seed == 1 else ()
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


class SQLiteMemoryCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MarkdownMemoryStore(self.root / "memory-bank" / "memories")
        self.path = self.root / ".paradigma" / "cache" / "catalog.sqlite3"
        self.catalog = SQLiteMemoryCatalog(
            self.path, self.store, path_base=self.root
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_rebuild_populates_all_projections_fts_verify_and_stats(self) -> None:
        second = self.store.create(record(2, status=MemoryStatus.CANDIDATE))
        first = self.store.create(record(1))

        rebuilt = self.catalog.rebuild()
        self.assertTrue(rebuilt.written)
        self.assertEqual(2, rebuilt.record_count)
        self.assertTrue(rebuilt.source_digest.startswith("sha256:"))

        connection = sqlite3.connect(self.path)
        try:
            meta = dict(connection.execute("SELECT key, value FROM catalog_meta"))
            row = connection.execute(
                "SELECT path, description, status, scope_namespace, confidence, "
                "provenance_summary, content_hash, source_hash "
                "FROM memories WHERE memory_id = ?",
                (first.record.memory_id,),
            ).fetchone()
            fts = connection.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH 'Searchable' "
                "ORDER BY memory_id"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(CATALOG_SCHEMA_VERSION, meta["catalog_schema_version"])
        self.assertEqual("2", meta["record_count"])
        self.assertEqual("memory-bank/memories/" + first.path.name, row[0])
        self.assertEqual("Searchable body number 1.", row[1])
        self.assertEqual("active", row[2])
        self.assertEqual("catalog-test", row[3])
        self.assertEqual(0.8, row[4])
        self.assertEqual("tool_result:tool-1", row[5])
        self.assertEqual(first.content_hash, row[6])
        self.assertEqual(first.source_hash, row[7])
        self.assertEqual([(memory_id(1),), (memory_id(2),)], fts)

        verification = self.catalog.verify()
        self.assertTrue(verification.current, verification.issues)
        stats = self.catalog.stats()
        self.assertEqual(2, stats.record_count)
        self.assertEqual(4, stats.tag_count)
        self.assertEqual(1, stats.relation_count)
        self.assertEqual((('active', 1), ('candidate', 1)), stats.status_counts)
        self.assertEqual((('semantic', 2),), stats.type_counts)

    def test_dry_run_validates_sources_without_creating_catalog(self) -> None:
        self.store.create(record())
        result = self.catalog.rebuild(dry_run=True)
        self.assertFalse(result.written)
        self.assertEqual(1, result.record_count)
        self.assertFalse(self.path.exists())

    def test_verify_detects_source_and_catalog_drift(self) -> None:
        created = self.store.create(record())
        self.catalog.rebuild()
        revised = replace(
            created.record,
            revision=2,
            content="Changed canonical content.",
            updated_at=NOW + timedelta(seconds=1),
        )
        self.store.update(revised, expected_source_hash=created.source_hash)

        source_drift = self.catalog.verify()
        self.assertFalse(source_drift.current)
        self.assertIn(
            "catalog source digest does not match Markdown", source_drift.issues
        )

        self.catalog.rebuild()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                "UPDATE memories SET title = 'tampered' WHERE memory_id = ?",
                (created.record.memory_id,),
            )
            connection.commit()
        finally:
            connection.close()
        row_drift = self.catalog.verify()
        self.assertFalse(row_drift.current)
        self.assertIn(
            "memory rows do not match canonical Markdown", row_drift.issues
        )

    def test_missing_catalog_is_reported_as_drift(self) -> None:
        result = self.catalog.verify()
        self.assertFalse(result.current)
        self.assertEqual(("catalog file is missing",), result.issues)

    def test_rebuild_rejects_invalid_managed_filename_instead_of_ignoring_it(self) -> None:
        self.store.root.mkdir(parents=True)
        (self.store.root / "MEM-invalid.md").write_text("not canonical", encoding="utf-8")
        with self.assertRaisesRegex(CatalogFailure, "invalid managed"):
            self.catalog.rebuild(dry_run=True)


class CatalogCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config_root = self.root / ".paradigma"
        config_root.mkdir(parents=True)
        (config_root / "config.yaml").write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: memory-bank/memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        MarkdownMemoryStore(self.root / "memory-bank" / "memories").create(record())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, dict[str, object]]:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [*arguments, "--project", str(self.root), "--format", "json"]
            )
        return exit_code, json.loads(output.getvalue())

    def test_catalog_commands_share_application_contract(self) -> None:
        preview_exit, preview = self.run_cli("catalog", "rebuild", "--dry-run")
        self.assertEqual(0, preview_exit)
        self.assertTrue(preview["dry_run"])
        self.assertFalse((self.root / ".paradigma/cache/catalog.sqlite3").exists())

        rebuild_exit, rebuild = self.run_cli("catalog", "rebuild")
        self.assertEqual(0, rebuild_exit)
        self.assertTrue(rebuild["changed"])
        self.assertEqual(1, rebuild["data"]["record_count"])

        verify_exit, verify = self.run_cli("catalog", "verify")
        self.assertEqual(0, verify_exit)
        self.assertTrue(verify["data"]["current"])

        stats_exit, stats = self.run_cli("catalog", "stats")
        self.assertEqual(0, stats_exit)
        self.assertEqual(1, stats["data"]["record_count"])


if __name__ == "__main__":
    unittest.main()
