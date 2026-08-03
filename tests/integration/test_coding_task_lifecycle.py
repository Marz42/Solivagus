from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
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

from paradigma.cli.main import main
from paradigma.runtime import ActiveSessionPointer, ActiveTaskPointer, CodingRuntimeStore


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


class CodingTaskLifecycleCliTests(unittest.TestCase):
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
""",
            encoding="utf-8",
        )
        self.store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.store.set_active_task(ActiveTaskPointer(None, NOW), expected_source_hash=None)
        self.store.set_active_session(
            ActiveSessionPointer(None, None, NOW), expected_source_hash=None
        )
        self.store.rebuild_projections()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_json(self, *arguments: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = main([*arguments, "--project", str(self.root), "--format", "json"])
        return code, json.loads(output.getvalue())

    def run_text(self, *arguments: str) -> tuple[int, str]:
        output = StringIO()
        with redirect_stdout(output):
            code = main([*arguments, "--project", str(self.root)])
        return code, output.getvalue()

    def start_args(self) -> tuple[str, ...]:
        return (
            "task",
            "start",
            "--task-id",
            "TASK-001",
            "--title",
            "Lifecycle",
            "--goal",
            "Enforce transitions.",
            "--workspace-id",
            "workspace-1",
            "--repository-id",
            "paradigma",
        )

    def test_default_dry_run_then_full_lifecycle_updates_yaml_and_projection(self) -> None:
        dry_code, dry = self.run_json(*self.start_args())
        self.assertEqual(0, dry_code)
        self.assertTrue(dry["dry_run"])
        self.assertFalse((self.store.tasks_root / "TASK-001.yaml").exists())

        start_code, start = self.run_json(*self.start_args(), "--write")
        self.assertEqual(0, start_code)
        self.assertEqual("active", start["data"]["task"]["status"])
        self.assertTrue(self.store.verify_projections().current)

        expected = (
            ("block", ("--reason", "Waiting for CI"), "blocked"),
            ("unblock", (), "active"),
            ("suspend", ("--reason", "Priority switch"), "suspended"),
            ("resume", (), "active"),
            ("complete", (), "completed"),
        )
        for command, extra, status in expected:
            with self.subTest(command=command):
                code, outcome = self.run_json(
                    "task", command, *extra, "--write"
                )
                self.assertEqual(0, code, outcome)
                self.assertEqual(status, outcome["data"]["task"]["status"])
                self.assertTrue(self.store.verify_projections().current)

        status_code, status = self.run_json("task", "status")
        self.assertEqual(0, status_code)
        self.assertFalse(status["data"]["active"])
        self.assertIn(
            "\n## Current Status\n\npending\n",
            (self.store.root / "active-task.md").read_text(encoding="utf-8"),
        )

    def test_illegal_transition_and_second_start_have_stable_errors(self) -> None:
        self.run_json(*self.start_args(), "--write")
        second_code, second = self.run_json(*self.start_args(), "--write")
        self.assertEqual(3, second_code)
        self.assertEqual("PD_TASK_ALREADY_ACTIVE", second["diagnostics"][0]["code"])

        invalid_code, invalid = self.run_json("task", "resume", "--write")
        self.assertEqual(3, invalid_code)
        self.assertEqual(
            "PD_TASK_INVALID_TRANSITION", invalid["diagnostics"][0]["code"]
        )

    def test_text_failure_renders_diagnostic_without_success_payload(self) -> None:
        self.run_json(*self.start_args(), "--write")

        code, output = self.run_text(*self.start_args(), "--write")

        self.assertEqual(3, code)
        self.assertIn("PD_TASK_ALREADY_ACTIVE", output)
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
