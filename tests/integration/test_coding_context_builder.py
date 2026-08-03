from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.application.coding_context import CodingContextError, build_context_manifest
from paradigma.cli.main import main
from paradigma.integrations.coding import (
    CodingSession,
    CodingTask,
    ContextPriority,
    ContextRequest,
    RepositoryScope,
)
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
from paradigma.runtime import ActiveSessionPointer, ActiveTaskPointer, CodingRuntimeStore
from paradigma.storage.catalog import SQLiteMemoryCatalog
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, 2, 20, tzinfo=timezone.utc)


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def memory(seed: int, **overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(seed),
        "memory_type": MemoryType.SEMANTIC,
        "title": f"Memory {seed}",
        "content": f"Context body {seed}",
        "scope": MemoryScope(
            namespace="coding",
            workspace_id="workspace-1",
            project_id="paradigma",
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
        "confidence": 1.0,
        "sensitivity": "internal",
        "tags": (f"memory-{seed}",),
        "relations": (),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


def concept(
    title: str,
    *,
    temperature: str = "warm",
    epistemic: str = "confirmed",
    symbols: tuple[str, ...] = (),
    relations: tuple[str, ...] = (),
    body: str = "Body",
) -> str:
    symbol_lines = "\n".join(f"    - {item}" for item in symbols) or "    []"
    relation_lines = "\n".join(f"      - {item}" for item in relations)
    relation_block = (
        "  relations:\n    related_to:\n" + relation_lines
        if relations
        else "  relations: {}"
    )
    return f"""---
type: paradigma-test
title: {title}
description: {title} context description.
tags: [test]
timestamp: 2026-07-24T02:20:00+00:00
paradigma:
  schema_version: "0.1"
  temperature: {temperature}
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: {epistemic}
  retrieval_hints:
    en: [context builder]
  symbols:
{symbol_lines}
{relation_block}
---

# {title}

{body}
"""


class CodingContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = self.root / ".paradigma" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.6.0"
knowledge_roots: [memory-bank/knowledge]
runtime_root: memory-bank/runtime
memory_root: memory-bank/memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        knowledge = self.root / "memory-bank" / "knowledge"
        knowledge.mkdir(parents=True)
        (knowledge / "architecture.md").write_text(
            concept(
                "Architecture",
                temperature="hot",
                symbols=("src/core",),
                relations=("/domain.md",),
            ),
            encoding="utf-8",
        )
        self.domain = knowledge / "domain.md"
        self.domain.write_text(
            concept("Domain", symbols=("ContextPlanner",), body="Deterministic context keyword."),
            encoding="utf-8",
        )
        (knowledge / "large.md").write_text(
            concept("Large", body="budgetword " * 2000), encoding="utf-8"
        )
        (knowledge / "deprecated.md").write_text(
            concept("Deprecated", temperature="hot", epistemic="deprecated"),
            encoding="utf-8",
        )

        runtime = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        scope = RepositoryScope("workspace-1", "paradigma")
        runtime.create_task(CodingTask("TASK-001", scope, "Context", "Build context", "active", NOW, NOW))
        runtime.set_active_task(ActiveTaskPointer("TASK-001", NOW), expected_source_hash=None)
        runtime.create_session(CodingSession("SESSION-001", "TASK-001", scope, "active", NOW, NOW))
        runtime.set_active_session(
            ActiveSessionPointer("SESSION-001", "TASK-001", NOW),
            expected_source_hash=None,
        )
        runtime.rebuild_projections()

        memory_store = MarkdownMemoryStore(self.root / "memory-bank" / "memories")
        memory_store.create(memory(
            1,
            title="Mandatory project memory",
            tags=("mandatory",),
            relations=(MemoryRelation("related_to", memory_id(2)),),
        ))
        memory_store.create(memory(
            2,
            title="Related implementation memory",
            tags=("symbol:ContextPlanner", "path:src/context"),
        ))
        memory_store.create(memory(
            3,
            title="Other task memory",
            scope=MemoryScope(
                namespace="coding",
                workspace_id="workspace-1",
                project_id="paradigma",
                task_id="TASK-OTHER",
            ),
            tags=("mandatory",),
        ))
        memory_store.create(memory(
            4,
            title="Expired memory",
            tags=("mandatory",),
            valid_from=NOW - timedelta(days=3),
            valid_until=NOW - timedelta(days=2),
        ))
        SQLiteMemoryCatalog(
            self.root / ".paradigma" / "cache" / "catalog.sqlite3",
            memory_store,
            path_base=self.root,
        ).rebuild()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_json(self, *args: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = main([*args, "--project", str(self.root), "--format", "json"])
        return code, json.loads(output.getvalue())

    def request(self, budget: int = 50000) -> ContextRequest:
        return ContextRequest(
            "Implement context",
            "TASK-001",
            explicit_paths=("src/context",),
            explicit_symbols=("ContextPlanner",),
            keywords=("budgetword",),
            budget_tokens=budget,
        )

    def test_deterministic_pipeline_reasons_scope_relations_and_budget(self) -> None:
        first = build_context_manifest(self.root, self.request())
        second = build_context_manifest(self.root, self.request())
        self.assertEqual(first, second)
        by_id = {item.document_id: item for item in first.documents}
        self.assertIn("memory-bank/knowledge/architecture.md", by_id)
        self.assertIn("memory-bank/knowledge/domain.md", by_id)
        self.assertIn(memory_id(1), by_id)
        self.assertIn(memory_id(2), by_id)
        self.assertTrue(all(item.reasons for item in first.documents))
        self.assertEqual(ContextPriority.REQUIRED, by_id[memory_id(2)].priority)
        self.assertTrue(
            any(item.reason.startswith("scope_filtered:task_id") for item in first.excluded)
        )
        self.assertTrue(
            any(item.reason == "epistemic_status_filtered:deprecated" for item in first.excluded)
        )
        self.assertTrue(
            any(item.reason.startswith("validity_filtered:") for item in first.excluded)
        )
        required = sum(
            item.estimated_tokens
            for item in first.documents
            if item.priority is ContextPriority.REQUIRED
        )
        trimmed = build_context_manifest(self.root, self.request(required))
        self.assertTrue(
            any(
                item.path == "memory-bank/knowledge/large.md"
                and item.reason == "budget_trimmed"
                for item in trimmed.excluded
            )
        )

    def test_cli_default_is_non_mutating_write_then_verify_detects_drift(self) -> None:
        arguments = (
            "context", "build",
            "--intent", "Implement context",
            "--task-id", "TASK-001",
            "--symbol", "ContextPlanner",
            "--budget", "50000",
        )
        dry_code, dry = self.run_json(*arguments)
        self.assertEqual(0, dry_code, dry)
        self.assertTrue(dry["dry_run"])
        manifest_path = self.root / "memory-bank" / "runtime" / "context-manifest.yaml"
        self.assertFalse(manifest_path.exists())

        write_code, written = self.run_json(*arguments, "--write")
        self.assertEqual(0, write_code, written)
        self.assertTrue(manifest_path.exists())
        repeat_code, repeated = self.run_json(*arguments, "--write")
        self.assertEqual(0, repeat_code, repeated)
        self.assertFalse(repeated["changed"])
        verify_code, verified = self.run_json("context", "verify")
        self.assertEqual(0, verify_code, verified)
        self.assertTrue(verified["data"]["current"])

        manifest_path.write_text("corrupt: true\n", encoding="utf-8")
        repair_code, repaired = self.run_json(*arguments, "--write")
        self.assertEqual(0, repair_code, repaired)
        self.assertTrue(repaired["changed"])

        self.domain.write_text(
            self.domain.read_text(encoding="utf-8") + "\nRepository state changed.\n",
            encoding="utf-8",
        )
        stale_code, stale = self.run_json("context", "verify")
        self.assertEqual(1, stale_code)
        self.assertEqual("PD_CONTEXT_MANIFEST_STALE", stale["diagnostics"][0]["code"])

    def test_task_mismatch_and_stale_catalog_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(CodingContextError, "active task"):
            build_context_manifest(
                self.root,
                ContextRequest("Wrong task", "TASK-OTHER", keywords=("context",)),
            )
        store = MarkdownMemoryStore(self.root / "memory-bank" / "memories")
        store.create(memory(5, title="Catalog drift"))
        with self.assertRaisesRegex(CodingContextError, "catalog must be current"):
            build_context_manifest(self.root, self.request())


if __name__ == "__main__":
    unittest.main()
