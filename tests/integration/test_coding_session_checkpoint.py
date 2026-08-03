from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.cli.main import main
from paradigma.integrations.coding import CodingTask, RepositoryScope
from paradigma.runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingCheckpointStore,
    CodingRuntimeStore,
)


NOW = datetime(2026, 7, 23, 0, 0, tzinfo=timezone.utc)


class CodingSessionCheckpointCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
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
        scope = RepositoryScope("workspace-1", "paradigma")
        self.store.create_task(
            CodingTask("TASK-001", scope, "Task", "Goal", "active", NOW, NOW)
        )
        self.store.set_active_task(ActiveTaskPointer("TASK-001", NOW), expected_source_hash=None)
        self.store.set_active_session(
            ActiveSessionPointer(None, None, NOW), expected_source_hash=None
        )
        self.store.rebuild_projections()
        self.narrative = self.root / "checkpoint.yaml"
        self.narrative.write_text(
            """summary: Session checkpoint
completed_work: [Implemented session lifecycle]
remaining_work: [Run full regression]
blockers: []
next_steps: [Complete the batch]
""",
            encoding="utf-8",
        )
        (self.root / "证据 文件.txt").write_text("evidence\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_json(self, *args: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = main([*args, "--project", str(self.root), "--format", "json"])
        return code, json.loads(output.getvalue())

    def test_session_checkpoint_handoff_and_end_full_chain(self) -> None:
        dry_code, dry = self.run_json(
            "session", "start", "--session-id", "SESSION-001", "--agent-id", "codex"
        )
        self.assertEqual(0, dry_code)
        self.assertTrue(dry["dry_run"])

        start_code, start = self.run_json(
            "session", "start", "--session-id", "SESSION-001", "--agent-id", "codex", "--write"
        )
        self.assertEqual(0, start_code)
        self.assertEqual("active", start["data"]["session"]["status"])

        dry_checkpoint_code, dry_checkpoint = self.run_json(
            "session", "checkpoint",
            "--checkpoint-id", "CHECKPOINT-DRY",
            "--input", str(self.narrative),
            "--test-command", "definitely-not-an-installed-command",
        )
        self.assertEqual(0, dry_checkpoint_code, dry_checkpoint)
        self.assertTrue(dry_checkpoint["dry_run"])
        self.assertFalse(
            (self.store.root / "checkpoints" / "CHECKPOINT-DRY.yaml").exists()
        )

        checkpoint_code, outcome = self.run_json(
            "session", "checkpoint",
            "--checkpoint-id", "CHECKPOINT-001",
            "--input", str(self.narrative),
            "--test-command", "python -c \"print('ok')\"",
            "--write",
        )
        self.assertEqual(0, checkpoint_code, outcome)
        stored = CodingCheckpointStore(self.store.root).read("CHECKPOINT-001")
        self.assertEqual("passed", stored.checkpoint.tests[0].status.value)
        self.assertTrue(stored.checkpoint.git.dirty)
        self.assertIn(".paradigma/config.yaml", stored.checkpoint.git.worktree_paths)
        self.assertIn("证据 文件.txt", stored.checkpoint.git.worktree_paths)
        handoff = (self.store.root / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("Session checkpoint", handoff)
        self.assertIn("Implemented session lifecycle", handoff)
        self.assertIn("passed", handoff)

        handoff_code, handoff_outcome = self.run_json("handoff", "build")
        self.assertEqual(0, handoff_code)
        self.assertTrue(handoff_outcome["data"]["current"])

        end_code, ended = self.run_json("session", "end", "--write")
        self.assertEqual(0, end_code)
        self.assertEqual("ended", ended["data"]["session"]["status"])
        status_code, status = self.run_json("session", "status")
        self.assertEqual(0, status_code)
        self.assertFalse(status["data"]["active"])
        self.assertTrue(self.store.verify_projections().current)
        ended_handoff = (self.store.root / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("Session checkpoint", ended_handoff)
        self.assertIn("(ended)", ended_handoff)


if __name__ == "__main__":
    unittest.main()
