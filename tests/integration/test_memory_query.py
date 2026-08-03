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

from paradigma.application.memory import query_memories
from paradigma.kernel import (
    MemoryQuery,
    MemoryRecord,
    MemoryRelation,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.storage.catalog import (
    CatalogQuery,
    CatalogQueryFailure,
    CatalogTextMode,
    SQLiteMemoryCatalog,
)
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def record(seed: int, **overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(seed),
        "memory_type": MemoryType.SEMANTIC,
        "title": f"Memory {seed}",
        "content": f"Body token-{seed}",
        "scope": MemoryScope(
            namespace="query-test",
            workspace_id="workspace-1",
            project_id="project-1",
            entity_ids=(f"entity-{seed}",),
        ),
        "provenance": (
            ProvenanceRef(
                source_type=ProvenanceType.TOOL_RESULT,
                source_id=f"source-{seed}",
                observed_at=NOW,
                actor="test",
            ),
        ),
        "status": MemoryStatus.ACTIVE,
        "revision": 1,
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        "confidence": 0.9,
        "sensitivity": "internal",
        "tags": ("shared", f"tag-{seed}"),
        "relations": (),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


class MemoryQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = MarkdownMemoryStore(self.root / "memory-bank" / "memories")
        self.path = self.root / ".paradigma" / "cache" / "catalog.sqlite3"
        self.catalog = SQLiteMemoryCatalog(
            self.path, self.store, path_base=self.root
        )
        first = record(
            1,
            title="Alpha architecture",
            content="Alpha kernel boundary",
            relations=(
                MemoryRelation("related_to", memory_id(2)),
                MemoryRelation("related_to", memory_id(3)),
                MemoryRelation("related_to", memory_id(4)),
            ),
        )
        second = record(
            2,
            title="Beta implementation",
            relations=(MemoryRelation("related_to", memory_id(5)),),
        )
        candidate = record(
            3, title="Alpha candidate", status=MemoryStatus.CANDIDATE
        )
        expired_interval = record(
            4,
            title="Old active memory",
            valid_from=NOW - timedelta(days=3),
            valid_until=NOW - timedelta(days=2),
        )
        third_hop = record(5, title="Third hop")
        for item in (first, second, candidate, expired_interval, third_hop):
            self.store.create(item)
        self.catalog.rebuild()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ids(self, request: CatalogQuery) -> list[str]:
        return [result.record.memory_id for result in self.catalog.query(request)]

    def test_id_path_keyword_fts_and_tag_queries_are_explainable(self) -> None:
        first_path = f"memory-bank/memories/{memory_id(1)}.md"
        cases = (
            (
                CatalogQuery(MemoryQuery(memory_ids=(memory_id(1),))),
                "memory_id",
                "memory_id:",
            ),
            (
                CatalogQuery(MemoryQuery(), paths=(first_path,)),
                "path",
                "path:",
            ),
            (
                CatalogQuery(
                    MemoryQuery(text="ALPHA"),
                    text_mode=CatalogTextMode.KEYWORD,
                ),
                "title",
                "keyword:ALPHA",
            ),
            (
                CatalogQuery(MemoryQuery(text="Alpha")),
                "title",
                "fts:Alpha",
            ),
            (
                CatalogQuery(MemoryQuery(tags=("tag-1",))),
                "tags",
                "tag:tag-1",
            ),
        )
        for request, field, reason in cases:
            with self.subTest(request=request):
                results = self.catalog.query(request)
                self.assertEqual([memory_id(1)], [item.record.memory_id for item in results])
                self.assertIn(field, results[0].matched_fields)
                self.assertTrue(
                    any(value.startswith(reason) for value in results[0].match_reasons)
                )

    def test_scope_status_and_inclusive_validity_filters_compose(self) -> None:
        scoped = CatalogQuery(
            MemoryQuery(
                scope=MemoryScope(
                    namespace="query-test",
                    project_id="project-1",
                    entity_ids=("entity-2",),
                ),
                valid_at=NOW,
            )
        )
        self.assertEqual([memory_id(2)], self.ids(scoped))

        candidates = CatalogQuery(
            MemoryQuery(statuses=(MemoryStatus.CANDIDATE,), valid_at=NOW)
        )
        self.assertEqual([memory_id(3)], self.ids(candidates))

        outside = CatalogQuery(
            MemoryQuery(memory_ids=(memory_id(4),), valid_at=NOW)
        )
        self.assertEqual([], self.ids(outside))
        boundary_record = self.store.read(memory_id(4))
        boundary = CatalogQuery(
            MemoryQuery(
                memory_ids=(memory_id(4),),
                valid_at=boundary_record.record.valid_until,
            )
        )
        self.assertEqual([memory_id(4)], self.ids(boundary))

    def test_relation_expansion_is_opt_in_filtered_and_exactly_one_hop(self) -> None:
        direct = CatalogQuery(MemoryQuery(memory_ids=(memory_id(1),)))
        self.assertEqual([memory_id(1)], self.ids(direct))

        expanded = CatalogQuery(
            MemoryQuery(
                memory_ids=(memory_id(1),),
                include_related=True,
                relation_types=("related_to",),
                valid_at=NOW,
            )
        )
        results = self.catalog.query(expanded)
        self.assertEqual([memory_id(1), memory_id(2)], [r.record.memory_id for r in results])
        self.assertEqual(memory_id(1), results[1].relation_source_id)
        self.assertEqual(("relation:related_to",), results[1].match_reasons)
        self.assertNotIn(memory_id(5), [result.record.memory_id for result in results])

    def test_structurally_identical_queries_have_stable_order_and_reasons(self) -> None:
        request = CatalogQuery(MemoryQuery(tags=("shared",), valid_at=NOW))
        first = self.catalog.query(request)
        second = self.catalog.query(request)
        projection = lambda values: [
            (item.record.memory_id, item.score, item.matched_fields, item.match_reasons)
            for item in values
        ]
        self.assertEqual(projection(first), projection(second))
        self.assertEqual(sorted(self.ids(request)), self.ids(request))

    def test_missing_stale_and_invalid_fts_catalogs_fail_explicitly(self) -> None:
        self.path.unlink()
        with self.assertRaisesRegex(CatalogQueryFailure, "rebuilt"):
            self.catalog.query(CatalogQuery())

        self.catalog.rebuild()
        created = self.store.read(memory_id(1))
        self.store.update(
            replace(
                created.record,
                revision=2,
                content="changed",
                updated_at=NOW + timedelta(seconds=1),
            ),
            expected_source_hash=created.source_hash,
        )
        with self.assertRaisesRegex(CatalogQueryFailure, "rebuilt"):
            self.catalog.query(CatalogQuery())

        self.catalog.rebuild()
        with self.assertRaisesRegex(CatalogQueryFailure, "invalid FTS"):
            self.catalog.query(CatalogQuery(MemoryQuery(text='"unterminated')))

    def test_application_api_uses_repository_config(self) -> None:
        config_root = self.root / ".paradigma"
        config_root.mkdir(parents=True, exist_ok=True)
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
        results = query_memories(
            self.root,
            CatalogQuery(MemoryQuery(memory_ids=(memory_id(1),))),
        )
        self.assertEqual(memory_id(1), results[0].record.memory_id)


class CatalogQueryValueTests(unittest.TestCase):
    def test_paths_and_text_mode_are_strict(self) -> None:
        request = CatalogQuery(
            paths=("memory-bank/memories/MEM-example.md",), text_mode="keyword"
        )
        self.assertEqual(CatalogTextMode.KEYWORD, request.text_mode)
        for path in ("/absolute.md", "../escape.md", "a\\b.md", " a.md"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    CatalogQuery(paths=(path,))
        with self.assertRaisesRegex(ValueError, "keyword or fts"):
            CatalogQuery(text_mode="semantic")


if __name__ == "__main__":
    unittest.main()
