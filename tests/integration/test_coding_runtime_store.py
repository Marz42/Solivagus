from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.integrations.coding import CodingSession, CodingTask, RepositoryScope
from paradigma.runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingRuntimeConflictError,
    CodingRuntimeNotFoundError,
    CodingRuntimeStore,
)
from paradigma.cli.main import main


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


def repository() -> RepositoryScope:
    return RepositoryScope("workspace-1", "paradigma")


def task() -> CodingTask:
    return CodingTask(
        "TASK-001",
        repository(),
        "Runtime facts",
        "Persist task and session facts in strict YAML.",
        "active",
        NOW,
        NOW,
    )


def session() -> CodingSession:
    return CodingSession(
        "SESSION-001",
        "TASK-001",
        repository(),
        "active",
        NOW,
        NOW,
        agent_id="codex",
    )


class CodingRuntimeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "memory-bank" / "runtime"
        self.store = CodingRuntimeStore(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_read_and_cas_update_increment_snapshot_revision(self) -> None:
        first = self.store.create_task(task())
        updated_value = replace(
            first.task,
            title="Updated runtime facts",
            updated_at=NOW + timedelta(seconds=1),
        )
        second = self.store.update_task(
            updated_value,
            expected_source_hash=first.source_hash,
        )

        self.assertEqual(1, first.snapshot_revision)
        self.assertEqual(2, second.snapshot_revision)
        self.assertEqual("Updated runtime facts", second.task.title)
        self.assertTrue(second.canonical)

        with self.assertRaisesRegex(CodingRuntimeConflictError, "changed"):
            self.store.update_task(
                replace(second.task, updated_at=NOW + timedelta(seconds=2)),
                expected_source_hash=first.source_hash,
            )

    def test_session_requires_task_and_preserves_identity_on_update(self) -> None:
        with self.assertRaises(CodingRuntimeNotFoundError):
            self.store.create_session(session())
        self.store.create_task(task())
        first = self.store.create_session(session())
        ended = replace(
            first.session,
            status="ended",
            updated_at=NOW + timedelta(seconds=2),
            ended_at=NOW + timedelta(seconds=1),
        )
        second = self.store.update_session(ended, expected_source_hash=first.source_hash)
        self.assertEqual("ended", second.session.status.value)
        self.assertEqual(2, second.snapshot_revision)

    def test_active_pointers_require_existing_consistent_snapshots_and_cas(self) -> None:
        task_snapshot = self.store.create_task(task())
        self.store.create_session(session())
        active_task = self.store.set_active_task(
            ActiveTaskPointer(task_snapshot.task.task_id, NOW),
            expected_source_hash=None,
        )
        active_session = self.store.set_active_session(
            ActiveSessionPointer("SESSION-001", "TASK-001", NOW),
            expected_source_hash=None,
        )

        self.assertEqual("TASK-001", active_task.pointer.task_id)
        self.assertEqual("SESSION-001", active_session.pointer.session_id)
        with self.assertRaisesRegex(CodingRuntimeConflictError, "requires"):
            self.store.set_active_task(
                ActiveTaskPointer("TASK-001", NOW),
                expected_source_hash=None,
            )
        with self.assertRaisesRegex(CodingRuntimeConflictError, "cleared"):
            self.store.set_active_task(
                ActiveTaskPointer(None, NOW + timedelta(seconds=1)),
                expected_source_hash=active_task.source_hash,
            )

    def test_markdown_projections_rebuild_and_detect_drift(self) -> None:
        self.store.create_task(task())
        self.store.create_session(session())
        self.store.set_active_task(ActiveTaskPointer("TASK-001", NOW), expected_source_hash=None)
        self.store.set_active_session(
            ActiveSessionPointer("SESSION-001", "TASK-001", NOW),
            expected_source_hash=None,
        )

        rebuilt = self.store.rebuild_projections()
        self.assertTrue(rebuilt.current)
        active = (self.root / "active-task.md").read_text(encoding="utf-8")
        handoff = (self.root / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("Generated from YAML facts", active)
        self.assertIn("TASK-001", active)
        self.assertIn("SESSION-001", handoff)

        (self.root / "active-task.md").write_text("manual drift\n", encoding="utf-8")
        self.assertFalse(self.store.verify_projections().current)
        self.assertTrue(self.store.rebuild_projections().current)

    def test_empty_pointers_produce_stable_pending_projections(self) -> None:
        self.store.set_active_task(ActiveTaskPointer(None, NOW), expected_source_hash=None)
        self.store.set_active_session(
            ActiveSessionPointer(None, None, NOW), expected_source_hash=None
        )
        self.assertTrue(self.store.rebuild_projections().current)
        active = (self.root / "active-task.md").read_text(encoding="utf-8")
        handoff = (self.root / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("\n## Current Status\n\npending\n", active)
        self.assertIn("No active CodingSession", handoff)


class CodingRuntimeCliTests(unittest.TestCase):
    def test_runtime_init_is_dry_run_by_default_and_idempotent_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".paradigma" / "config.yaml"
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
            runtime = root / "memory-bank" / "runtime"

            dry_code, dry = self._json("runtime", "init", "--project", str(root))
            self.assertEqual(0, dry_code)
            self.assertTrue(dry["dry_run"])
            self.assertTrue(dry["data"]["would_change"])
            self.assertFalse(runtime.exists())

            write_code, written = self._json(
                "runtime", "init", "--project", str(root), "--write"
            )
            self.assertEqual(0, write_code)
            self.assertTrue(written["changed"])
            self.assertTrue(written["data"]["task_pointer_created"])
            self.assertTrue(written["data"]["session_pointer_created"])
            store = CodingRuntimeStore(runtime)
            self.assertIsNone(store.read_active_task().pointer.task_id)
            self.assertIsNone(store.read_active_session().pointer.session_id)
            self.assertTrue(store.verify_projections().current)

            repeat_code, repeat = self._json(
                "runtime", "init", "--project", str(root), "--write"
            )
            self.assertEqual(0, repeat_code)
            self.assertFalse(repeat["changed"])
            self.assertFalse(repeat["data"]["would_change"])

            handoff = runtime / "handoff.md"
            handoff.write_text("drift\n", encoding="utf-8")
            drift_code, drift = self._json(
                "runtime", "init", "--project", str(root)
            )
            self.assertEqual(0, drift_code)
            self.assertTrue(drift["data"]["would_change"])
            self.assertEqual("drift\n", handoff.read_text(encoding="utf-8"))
            repair_code, repair = self._json(
                "runtime", "init", "--project", str(root), "--write"
            )
            self.assertEqual(0, repair_code)
            self.assertTrue(repair["changed"])
            self.assertTrue(store.verify_projections().current)

    def test_runtime_rebuild_and_verify_share_structured_application_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".paradigma" / "config.yaml"
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
            store = CodingRuntimeStore(root / "memory-bank" / "runtime")
            store.set_active_task(ActiveTaskPointer(None, NOW), expected_source_hash=None)
            store.set_active_session(
                ActiveSessionPointer(None, None, NOW), expected_source_hash=None
            )

            rebuild_code, rebuild = self._json(
                "runtime", "rebuild", "--project", str(root)
            )
            verify_code, verify = self._json(
                "runtime", "verify", "--project", str(root)
            )
            self.assertEqual(0, rebuild_code)
            self.assertTrue(rebuild["data"]["written"])
            self.assertEqual(0, verify_code)
            self.assertTrue(verify["data"]["current"])

            (root / "memory-bank" / "runtime" / "handoff.md").write_text(
                "drift\n", encoding="utf-8"
            )
            stale_code, stale = self._json(
                "runtime", "verify", "--project", str(root)
            )
            self.assertEqual(1, stale_code)
            self.assertEqual(
                "PD_CODING_RUNTIME_PROJECTION_STALE",
                stale["diagnostics"][0]["code"],
            )
            before = (root / "memory-bank" / "runtime" / "handoff.md").read_bytes()
            dry_code, dry = self._json(
                "runtime", "rebuild", "--project", str(root), "--dry-run"
            )
            self.assertEqual(0, dry_code)
            self.assertTrue(dry["dry_run"])
            self.assertTrue(dry["data"]["would_change"])
            self.assertEqual(
                before,
                (root / "memory-bank" / "runtime" / "handoff.md").read_bytes(),
            )

    @staticmethod
    def _json(*arguments: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = main([*arguments, "--format", "json"])
        return code, json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
