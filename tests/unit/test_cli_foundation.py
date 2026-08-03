from __future__ import annotations

from contextlib import redirect_stdout
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

from paradigma.application.indexing import index_rebuild_outcome
from paradigma.cli.main import main


def run_cli(*args: str) -> tuple[int, str]:
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(list(args))
    return exit_code, output.getvalue()


class UnifiedCliFoundationTests(unittest.TestCase):
    def test_version_json_is_structured_and_side_effect_free(self) -> None:
        exit_code, output = run_cli(
            "version", "--project", str(ROOT), "--format", "json", "--dry-run"
        )
        self.assertEqual(0, exit_code)
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual("0.7.0", payload["data"]["distribution_version"])

    def test_version_missing_root_is_a_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exit_code, output = run_cli(
                "version", "--project", temporary, "--format", "json"
            )
        self.assertEqual(1, exit_code)
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertEqual("PD_VERSION_READ_ERROR", payload["diagnostics"][0]["code"])

    def test_config_validate_and_index_verify_commands(self) -> None:
        config_exit, config_output = run_cli(
            "config", "validate", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(0, config_exit)
        payload = json.loads(config_output)["data"]
        self.assertEqual("0.4", payload["config_schema_version"])
        self.assertEqual("memory-bank/runtime", payload["runtime_root"])
        self.assertEqual("memory-bank/memories", payload["memory_root"])
        self.assertEqual(".paradigma/cache/catalog.sqlite3", payload["catalog_path"])

        index_exit, index_output = run_cli(
            "index", "verify", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(0, index_exit)
        self.assertEqual(0, json.loads(index_output)["data"]["stale"])

        runtime_exit, runtime_output = run_cli(
            "runtime", "verify", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(0, runtime_exit)
        self.assertTrue(json.loads(runtime_output)["data"]["current"])

    def test_aggregate_check_returns_six_structured_steps(self) -> None:
        exit_code, output = run_cli(
            "check", "--project", str(ROOT), "--format", "json", "--dry-run"
        )
        self.assertEqual(0, exit_code)
        payload = json.loads(output)
        self.assertEqual(6, payload["data"]["passed"])
        self.assertEqual(6, payload["data"]["total"])
        self.assertEqual(
            ["version", "lint", "links", "index verify", "hot-size", "design"],
            [step["name"] for step in payload["data"]["steps"]],
        )

    def test_self_diagnose_is_structured_and_gap_free(self) -> None:
        exit_code, output = run_cli(
            "diagnose",
            "--project",
            str(ROOT),
            "--upstream",
            str(ROOT),
            "--format",
            "json",
            "--dry-run",
        )
        self.assertEqual(0, exit_code)
        payload = json.loads(output)
        self.assertEqual("0.7.0", payload["data"]["detected_version"])
        self.assertEqual(0, payload["data"]["summary"]["total"])

    def test_index_rebuild_dry_run_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            knowledge = root / "memory-bank" / "knowledge"
            config_root.mkdir(parents=True)
            knowledge.mkdir(parents=True)
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
reserved_filenames: [index.md, log.md]
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )
            (knowledge / "index.md").write_text("# Navigation\n", encoding="utf-8")
            (knowledge / "concept.md").write_text(
                """---
type: test-concept
title: Test
description: Test.
---

# Test
""",
                encoding="utf-8",
            )
            index_rebuild_outcome(root)
            cache = config_root / "cache" / "knowledge-index.json"
            cache.write_text("broken\n", encoding="utf-8")
            before = cache.read_bytes()

            exit_code, output = run_cli(
                "index",
                "rebuild",
                "--project",
                str(root),
                "--format",
                "json",
                "--dry-run",
            )
            self.assertEqual(0, exit_code)
            payload = json.loads(output)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(1, payload["data"]["would_update"])
            self.assertEqual(before, cache.read_bytes())

    def test_task_archive_defaults_to_dry_run_and_write_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active = root / "memory-bank" / "runtime" / "active-task.md"
            template = (
                root
                / "memory-bank-template"
                / "runtime"
                / "active-task.template.md"
            )
            active.parent.mkdir(parents=True)
            template.parent.mkdir(parents=True)
            active.write_text(
                """# Active Task

## Task ID

TASK-CLI

## Current Status

completed

## Notes
""",
                encoding="utf-8",
            )
            template.write_text(
                """---
timestamp: YYYY-MM-DDTHH:mm:ssZ
---

# Active Task

## Task ID

## Current Status

pending

## Notes
""",
                encoding="utf-8",
            )
            before = active.read_bytes()

            preview_exit, preview_output = run_cli(
                "task", "archive", "--project", str(root), "--format", "json"
            )
            self.assertEqual(0, preview_exit)
            self.assertTrue(json.loads(preview_output)["dry_run"])
            self.assertEqual(before, active.read_bytes())

            write_exit, write_output = run_cli(
                "task",
                "archive",
                "--project",
                str(root),
                "--format",
                "json",
                "--write",
            )
            self.assertEqual(0, write_exit)
            self.assertTrue(json.loads(write_output)["changed"])
            self.assertIn("\n\npending\n", active.read_text(encoding="utf-8"))
            self.assertEqual(
                1,
                len(list((root / "memory-bank" / "logs" / "progress").glob("*.md"))),
            )

    def test_legacy_archive_refuses_yaml_runtime_repository(self) -> None:
        exit_code, output = run_cli(
            "task", "archive", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(3, exit_code)
        self.assertEqual(
            "PD_ARCHIVE_YAML_RUNTIME",
            json.loads(output)["diagnostics"][0]["code"],
        )


if __name__ == "__main__":
    unittest.main()
