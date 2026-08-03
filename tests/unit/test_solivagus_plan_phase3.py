from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.plan import run_plan_stage
from solivagus.planning.partition_builder import PartitionBudget, build_cache_partitions
from solivagus.planning.planner import PlanningConfig, plan_from_markdown
from solivagus.planning.tokenizer import TokenMode, approximate_token_count
from solivagus.planning.unit_builder import UnitBudget, build_translation_units
from solivagus.structure.models import NodeType
from solivagus.structure.parser import parse_markdown_structure
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


SAMPLE_MD = """# Title

<!-- source-page: 1 -->

Intro paragraph with some words.

## Method

```python
print("hi")
```

Equation:

$$
E = mc^2
$$

<table><tr><td>a</td><td>b</td></tr></table>

### Details

More prose here that should stay with the subsection.
"""


class StructureParserTests(unittest.TestCase):
    def test_classifies_protected_and_headings(self) -> None:
        nodes = parse_markdown_structure(SAMPLE_MD)
        types = [n.node_type for n in nodes]
        self.assertIn(NodeType.HEADING, types)
        self.assertIn(NodeType.CODE, types)
        self.assertIn(NodeType.FORMULA, types)
        self.assertIn(NodeType.HTML_TABLE, types)
        self.assertIn(NodeType.PAGE_MARKER, types)
        heading = next(n for n in nodes if n.node_type == NodeType.HEADING and n.heading_level == 1)
        self.assertEqual(heading.heading_path, "Title")
        method = next(n for n in nodes if n.heading_level == 2)
        self.assertIn("Method", method.heading_path)

    def test_html_table_is_single_node(self) -> None:
        md = "Before\n\n<table><tr><td>1</td></tr></table>\n\nAfter\n"
        nodes = parse_markdown_structure(md)
        tables = [n for n in nodes if n.node_type == NodeType.HTML_TABLE]
        self.assertEqual(len(tables), 1)
        self.assertIn("<table>", tables[0].source_text)


class PlanningTests(unittest.TestCase):
    def test_units_do_not_split_table_or_formula(self) -> None:
        nodes = parse_markdown_structure(SAMPLE_MD)
        for node in nodes:
            node.token_count = approximate_token_count(node.source_text)
        units = build_translation_units(nodes, budget=UnitBudget(target_tokens=50, max_tokens=200))
        joined = "\n".join(u.source_text for u in units)
        self.assertIn("<table>", joined)
        self.assertIn("E = mc^2", joined)
        # Table HTML should appear intact in exactly one unit.
        hits = sum(1 for u in units if "<table>" in u.source_text and "</table>" in u.source_text)
        self.assertEqual(hits, 1)

    def test_plan_idempotent_hashes(self) -> None:
        plan_a = plan_from_markdown(SAMPLE_MD, PlanningConfig())
        plan_b = plan_from_markdown(SAMPLE_MD, PlanningConfig())
        self.assertEqual(plan_a.config_hash, plan_b.config_hash)
        self.assertEqual(
            [u.source_hash for u in plan_a.units],
            [u.source_hash for u in plan_b.units],
        )
        self.assertEqual(plan_a.token_mode, TokenMode.APPROXIMATE.value)

    def test_partition_first_budget(self) -> None:
        # Build many tiny units and ensure first partition prefers 96k target semantics
        # via a scaled-down budget for the test.
        from solivagus.planning.unit_builder import PlannedUnit

        units = [
            PlannedUnit(
                unit_key=f"u{i:05d}",
                sequence_index=i,
                source_text=f"chunk {i}\n",
                source_hash=sha256_text(f"chunk {i}"),
                source_tokens=40_000,
                estimated_output_tokens=1000,
                heading_path="",
            )
            for i in range(1, 6)
        ]
        parts = build_cache_partitions(
            units,
            budget=PartitionBudget(
                first_target_tokens=96_000,
                target_tokens=220_000,
                max_tokens=300_000,
            ),
        )
        self.assertGreaterEqual(len(parts), 2)
        self.assertLessEqual(parts[0].source_tokens, 300_000)
        # First partition should close near the first target (2 * 40k = 80k < 96k,
        # third unit would push to 120k → flush after reaching target).
        self.assertLessEqual(parts[0].source_tokens, 120_000)


class PlanStageTests(unittest.TestCase):
    def test_plan_stage_replaces_seed_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            (artifact / "source.md").write_text(SAMPLE_MD, encoding="utf-8")
            (artifact / "units").mkdir()
            (artifact / "units" / "u00001.source.md").write_text("seed\n", encoding="utf-8")

            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            with Database(state_db_path(root)) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="plan-test-sha",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                )
                db.replace_units(
                    doc_id,
                    [
                        {
                            "unit_key": "u00001",
                            "sequence_index": 1,
                            "source_text": "seed",
                            "source_hash": sha256_text("seed"),
                            "status": UnitStatus.PENDING.value,
                            "source_file": "units/u00001.source.md",
                        }
                    ],
                )
                result = run_plan_stage(db, document_id=doc_id, settings=settings, force=True)
                self.assertFalse(result["skipped"])
                self.assertGreater(result["unit_count"], 0)
                self.assertGreater(result["node_count"], 0)
                units = db.list_units(doc_id)
                self.assertTrue(all(u["source_text"] != "seed" for u in units))
                self.assertTrue(db.list_partitions(doc_id))
                self.assertTrue(db.list_structural_nodes(doc_id))
                self.assertTrue((artifact / "plan-report.json").is_file())

                again = run_plan_stage(db, document_id=doc_id, settings=settings, force=False)
                self.assertTrue(again["skipped"])


if __name__ == "__main__":
    unittest.main()
