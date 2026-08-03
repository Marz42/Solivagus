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

from paradigma.application.coding_sessions import (
    CodingSessionLifecycleError,
    checkpoint_session_outcome,
    end_session_outcome,
    start_session_outcome,
)
from paradigma.integrations.coding import CodingTask, RepositoryScope
from paradigma.runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingCheckpointStore,
    CodingRuntimeConflictError,
    CodingRuntimeStore,
)
from paradigma.errors import AtomicWriteFailure


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


class CodingSessionFailureTests(unittest.TestCase):
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
        scope = RepositoryScope("workspace-1", "paradigma")
        store.create_task(CodingTask("TASK-001", scope, "Task", "Goal", "active", NOW, NOW))
        store.set_active_task(ActiveTaskPointer("TASK-001", NOW), expected_source_hash=None)
        store.set_active_session(ActiveSessionPointer(None, None, NOW), expected_source_hash=None)
        store.rebuild_projections()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def start(self, at=NOW):
        return start_session_outcome(
            self.root,
            session_id="SESSION-001",
            agent_id="codex",
            write=True,
            at=at,
        )

    def test_start_retry_recovers_session_snapshot_after_pointer_failure(self) -> None:
        with mock.patch.object(
            CodingRuntimeStore,
            "set_active_session",
            side_effect=CodingRuntimeConflictError("injected"),
        ):
            with self.assertRaises(CodingSessionLifecycleError):
                self.start()
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("active", store.read_session("SESSION-001").session.status.value)
        self.assertIsNone(store.read_active_session().pointer.session_id)
        self.assertTrue(self.start(NOW + timedelta(seconds=1)).ok)

    def test_start_retry_rebuilds_after_projection_failure(self) -> None:
        with mock.patch.object(
            CodingRuntimeStore,
            "rebuild_projections",
            side_effect=AtomicWriteFailure(
                self.root / "memory-bank" / "runtime" / "handoff.md",
                "atomic replace",
                OSError("injected"),
            ),
        ):
            with self.assertRaises(AtomicWriteFailure):
                self.start()
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("SESSION-001", store.read_active_session().pointer.session_id)
        self.assertTrue(self.start(NOW + timedelta(seconds=1)).ok)
        self.assertTrue(store.verify_projections().current)

    def test_checkpoint_retry_attaches_existing_append_only_fact(self) -> None:
        self.start()
        with mock.patch.object(
            CodingRuntimeStore,
            "update_session",
            side_effect=CodingRuntimeConflictError("injected"),
        ):
            with self.assertRaises(CodingSessionLifecycleError):
                checkpoint_session_outcome(
                    self.root,
                    checkpoint_id="CHECKPOINT-001",
                    narrative={"summary": "Stable fact"},
                    write=True,
                    at=NOW + timedelta(seconds=1),
                )
        checkpoints = CodingCheckpointStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("Stable fact", checkpoints.read("CHECKPOINT-001").checkpoint.summary)
        recovered = checkpoint_session_outcome(
            self.root,
            checkpoint_id="CHECKPOINT-001",
            narrative={"summary": "Retry text is ignored for existing ID"},
            write=True,
            at=NOW + timedelta(seconds=2),
        )
        self.assertTrue(recovered.ok)
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("CHECKPOINT-001", store.read_session("SESSION-001").session.current_checkpoint_id)
        self.assertEqual("Stable fact", checkpoints.read("CHECKPOINT-001").checkpoint.summary)

    def test_end_retry_clears_pointer_but_preserves_last_session_handoff(self) -> None:
        self.start()
        with mock.patch.object(
            CodingRuntimeStore,
            "set_active_session",
            side_effect=CodingRuntimeConflictError("injected"),
        ):
            with self.assertRaises(CodingSessionLifecycleError):
                end_session_outcome(
                    self.root, write=True, at=NOW + timedelta(seconds=1)
                )
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        self.assertEqual("ended", store.read_session("SESSION-001").session.status.value)
        recovered = end_session_outcome(
            self.root, write=True, at=NOW + timedelta(seconds=2)
        )
        self.assertTrue(recovered.ok)
        pointer = store.read_active_session().pointer
        self.assertIsNone(pointer.session_id)
        self.assertEqual("SESSION-001", pointer.last_session_id)

    def test_end_retry_rebuilds_after_projection_failure(self) -> None:
        self.start()
        with mock.patch.object(
            CodingRuntimeStore,
            "rebuild_projections",
            side_effect=AtomicWriteFailure(
                self.root / "memory-bank" / "runtime" / "handoff.md",
                "atomic replace",
                OSError("injected"),
            ),
        ):
            with self.assertRaises(AtomicWriteFailure):
                end_session_outcome(
                    self.root, write=True, at=NOW + timedelta(seconds=1)
                )
        store = CodingRuntimeStore(self.root / "memory-bank" / "runtime")
        pointer = store.read_active_session().pointer
        self.assertIsNone(pointer.session_id)
        self.assertEqual("SESSION-001", pointer.last_session_id)
        self.assertTrue(
            end_session_outcome(
                self.root, write=True, at=NOW + timedelta(seconds=2)
            ).ok
        )
        self.assertTrue(store.verify_projections().current)


if __name__ == "__main__":
    unittest.main()
