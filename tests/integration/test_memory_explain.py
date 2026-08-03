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

from paradigma.application.memory import explain_memory
from paradigma.application.mutations import commit_memory, forget_memory, propose_memory
from paradigma.application.mutations import revise_memory
from paradigma.cli.main import main
from paradigma.kernel import MemoryStatus, generate_memory_id


NOW = datetime(2026, 7, 24, 4, 0, tzinfo=timezone.utc)


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def payload(
    title: str,
    content: str,
    *,
    relations: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "memory_type": "semantic",
        "title": title,
        "content": content,
        "scope": {
            "namespace": "explain-test",
            "workspace_id": "workspace-1",
            "project_id": "project-1",
            "entity_ids": ["entity-1"],
        },
        "provenance": [
            {
                "source_type": "web_source",
                "source_uri": "https://example.test/source",
                "source_id": "source-1",
                "observed_at": NOW.isoformat(),
                "excerpt_hash": "1" * 64,
                "actor": "collector",
            }
        ],
        "validity": {
            "from": (NOW - timedelta(days=1)).isoformat(),
            "until": (NOW + timedelta(days=1)).isoformat(),
        },
        "confidence": 0.85,
        "sensitivity": "internal",
        "tags": ["explain", "golden"],
        "relations": relations or [],
    }


class MemoryExplainCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
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
        target = propose_memory(
            self.root,
            payload("Related target", "Supporting memory"),
            memory_id=memory_id(2),
            at=NOW,
            write=True,
        )
        self.target = commit_memory(
            self.root,
            target.record.memory_id,
            expected_source_hash=target.source_hash,
            at=NOW + timedelta(seconds=1),
            write=True,
        )
        source = propose_memory(
            self.root,
            payload(
                "Alpha source",
                "Alpha searchable evidence",
                relations=[
                    {
                        "relation_type": "related_to",
                        "target_memory_id": self.target.record.memory_id,
                    }
                ],
            ),
            memory_id=memory_id(1),
            at=NOW,
            write=True,
        )
        self.source = commit_memory(
            self.root,
            source.record.memory_id,
            expected_source_hash=source.source_hash,
            at=NOW + timedelta(seconds=1),
            write=True,
        )
        self.candidate = propose_memory(
            self.root,
            payload("Candidate note", "Not active"),
            memory_id=memory_id(3),
            at=NOW,
            write=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_json(self, *arguments: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [*arguments, "--project", str(self.root), "--format", "json"]
            )
        return exit_code, json.loads(output.getvalue())

    def test_query_cli_returns_every_required_explain_field_and_relation_source(self) -> None:
        exit_code, outcome = self.run_json(
            "memory",
            "query",
            "Alpha",
            "--include-related",
            "--relation-type",
            "related_to",
        )
        self.assertEqual(0, exit_code)
        self.assertEqual(2, outcome["data"]["count"])
        direct, related = outcome["data"]["results"]
        required = {
            "match_reasons",
            "matched_fields",
            "scope",
            "validity",
            "status",
            "provenance",
            "confidence",
            "relation_source_id",
            "warnings",
        }
        self.assertTrue(required.issubset(direct))
        self.assertIn("fts:Alpha", direct["match_reasons"])
        self.assertIn("validity not evaluated", direct["warnings"])
        self.assertEqual(self.source.record.memory_id, related["relation_source_id"])
        self.assertEqual(["relation:related_to"], related["match_reasons"])

    def test_explicit_non_active_query_has_exclusion_warning(self) -> None:
        exit_code, outcome = self.run_json(
            "memory",
            "query",
            "--memory-id",
            self.candidate.record.memory_id,
            "--status",
            "candidate",
            "--valid-at",
            NOW.isoformat(),
        )
        self.assertEqual(0, exit_code)
        result = outcome["data"]["results"][0]
        self.assertEqual("candidate", result["status"])
        self.assertEqual(
            ["excluded from ordinary queries: status candidate"],
            result["warnings"],
        )

    def test_query_cli_structured_scope_validation_is_explicit(self) -> None:
        exit_code, outcome = self.run_json(
            "memory", "query", "--project-id", "project-1"
        )
        self.assertEqual(2, exit_code)
        self.assertEqual(
            "PD_MEMORY_INPUT_ERROR", outcome["diagnostics"][0]["code"]
        )
        relation_exit, relation = self.run_json(
            "memory", "query", "--relation-type", "related_to"
        )
        self.assertEqual(2, relation_exit)
        self.assertIn("include_related", relation["diagnostics"][0]["message"])

    def test_explain_uses_canonical_truth_and_reports_catalog_or_status_warnings(self) -> None:
        exit_code, outcome = self.run_json(
            "memory",
            "explain",
            self.source.record.memory_id,
            "--at",
            NOW.isoformat(),
        )
        self.assertEqual(0, exit_code)
        data = outcome["data"]
        self.assertTrue(data["catalog_current"])
        self.assertTrue(data["ordinary_status_eligible"])
        self.assertTrue(data["valid_at_evaluation"])
        self.assertEqual("https://example.test/source", data["provenance"][0]["source_uri"])
        self.assertEqual(0.85, data["confidence"])
        self.assertEqual([], data["warnings"])

        forgotten = forget_memory(
            self.root,
            self.source.record.memory_id,
            expected_source_hash=self.source.source_hash,
            at=NOW + timedelta(seconds=2),
            write=True,
        )
        explanation = explain_memory(self.root, forgotten.record.memory_id, at=NOW)
        self.assertEqual(MemoryStatus.TOMBSTONED, explanation.stored.record.status)
        self.assertIn(
            "excluded from ordinary queries: status tombstoned",
            explanation.warnings,
        )

        catalog = self.root / ".paradigma" / "cache" / "catalog.sqlite3"
        catalog.unlink()
        missing = explain_memory(self.root, self.target.record.memory_id, at=NOW)
        self.assertFalse(missing.catalog_current)
        self.assertTrue(any("catalog file is missing" in item for item in missing.warnings))

    def test_text_rendering_is_utf8_safe_and_human_readable(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "memory",
                    "explain",
                    self.source.record.memory_id,
                    "--project",
                    str(self.root),
                    "--format",
                    "text",
                ]
            )
        self.assertEqual(0, exit_code)
        self.assertIn("scope:", output.getvalue())
        self.assertIn(self.source.record.memory_id, output.getvalue())

    def test_phase2_golden_propose_commit_query_explain_revise_forget_chain(self) -> None:
        identifier = memory_id(9)
        proposed = propose_memory(
            self.root,
            payload("Golden lifecycle", "Golden initial"),
            memory_id=identifier,
            at=NOW,
            write=True,
        )
        self.assertEqual(1, proposed.record.revision)
        committed = commit_memory(
            self.root,
            identifier,
            expected_source_hash=proposed.source_hash,
            at=NOW + timedelta(seconds=1),
            write=True,
        )
        query_exit, queried = self.run_json(
            "memory", "query", "--memory-id", identifier
        )
        self.assertEqual(0, query_exit)
        self.assertEqual(identifier, queried["data"]["results"][0]["memory_id"])
        explain_exit, explained = self.run_json("memory", "explain", identifier)
        self.assertEqual(0, explain_exit)
        self.assertEqual(2, explained["data"]["revision"])
        revised = revise_memory(
            self.root,
            identifier,
            {
                "content": "Golden revised",
                "provenance": [
                    {
                        "source_type": "user_statement",
                        "source_id": "golden-revision",
                    }
                ],
            },
            expected_source_hash=committed.source_hash,
            at=NOW + timedelta(seconds=2),
            write=True,
        )
        self.assertEqual(3, revised.record.revision)
        forgotten = forget_memory(
            self.root,
            identifier,
            expected_source_hash=revised.source_hash,
            at=NOW + timedelta(seconds=3),
            write=True,
        )
        self.assertEqual(4, forgotten.record.revision)
        _, after = self.run_json("memory", "query", "--memory-id", identifier)
        self.assertEqual(0, after["data"]["count"])


if __name__ == "__main__":
    unittest.main()
