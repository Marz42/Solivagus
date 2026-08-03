from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.application.coding_tasks import (
    CodingTaskLifecycleError,
    start_task_outcome,
    transition_task_outcome,
)
from paradigma.runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingRuntimeConflictError,
    CodingRuntimeStore,
)


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


class CodingTaskLifecycleFailureTests(unittest.TestCase):
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
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        store.set_active_task(ActiveTaskPointer(None, NOW), expected_source_hash=None)
        store.set_active_session(
            ActiveSessionPointer(None, None, NOW), expected_source_hash=None
        )
        store.rebuild_projections()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def start(self, at=NOW):
        return start_task_outcome(
            self.root,
            task_id="TASK-001",
            title="Lifecycle",
            goal="Recover interrupted mutations.",
            workspace_id="workspace-1",
            repository_id="paradigma",
            write=True,
            at=at,
        )

    def test_start_retry_recovers_orphan_active_snapshot_after_pointer_failure(self) -> None:
        failure = CodingRuntimeConflictError("injected pointer failure")
        with mock.patch.object(
            CodingRuntimeStore, "set_active_task", side_effect=failure
        ):
            with self.assertRaises(CodingTaskLifecycleError):
                self.start()

        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("active", store.read_task("TASK-001").task.status.value)
        self.assertIsNone(store.read_active_task().pointer.task_id)

        recovered = self.start(at=NOW + timedelta(seconds=1))
        self.assertTrue(recovered.ok)
        self.assertEqual("TASK-001", store.read_active_task().pointer.task_id)

    def test_terminal_retry_clears_pointer_after_interrupted_second_write(self) -> None:
        self.start()
        with mock.patch.object(
            CodingRuntimeStore,
            "set_active_task",
            side_effect=CodingRuntimeConflictError("injected clear failure"),
        ):
            with self.assertRaises(CodingTaskLifecycleError):
                transition_task_outcome(
                    self.root,
                    "complete",
                    write=True,
                    at=NOW + timedelta(seconds=1),
                )

        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("completed", store.read_task("TASK-001").task.status.value)
        self.assertEqual("TASK-001", store.read_active_task().pointer.task_id)

        recovered = transition_task_outcome(
            self.root,
            "complete",
            write=True,
            at=NOW + timedelta(seconds=2),
        )
        self.assertTrue(recovered.ok)
        self.assertIsNone(store.read_active_task().pointer.task_id)


if __name__ == "__main__":
    unittest.main()
