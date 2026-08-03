from __future__ import annotations

from dataclasses import replace
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

from paradigma.application.runtime import coding_runtime_init_outcome
from paradigma.errors import AtomicWriteFailure
from paradigma.integrations.coding import CodingTask, RepositoryScope
from paradigma.runtime import CodingRuntimeStorageError, CodingRuntimeStore


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


def task() -> CodingTask:
    return CodingTask(
        "TASK-001",
        RepositoryScope("workspace-1", "paradigma"),
        "Runtime",
        "Protect YAML facts.",
        "active",
        NOW,
        NOW,
    )


class CodingRuntimeFailureTests(unittest.TestCase):
    def test_runtime_init_recovers_after_partial_pointer_initialization(self) -> None:
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

            with mock.patch.object(
                CodingRuntimeStore,
                "set_active_session",
                side_effect=CodingRuntimeStorageError("injected interruption"),
            ):
                with self.assertRaises(CodingRuntimeStorageError):
                    coding_runtime_init_outcome(root, write=True, at=NOW)

            store = CodingRuntimeStore(runtime)
            self.assertIsNone(store.read_active_task().pointer.task_id)
            self.assertFalse((runtime / "active-session.yaml").exists())

            recovered = coding_runtime_init_outcome(root, write=True, at=NOW)
            self.assertTrue(recovered.changed)
            self.assertFalse(recovered.data["task_pointer_created"])
            self.assertTrue(recovered.data["session_pointer_created"])
            self.assertTrue(store.verify_projections().current)

    def test_snapshot_replace_failure_preserves_previous_fact_and_cleans_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CodingRuntimeStore(Path(temporary) / "runtime")
            first = store.create_task(task())
            before = first.path.read_bytes()
            changed = replace(first.task, updated_at=NOW + timedelta(seconds=1))

            failure = AtomicWriteFailure(first.path, "replace", OSError("injected"))
            with mock.patch(
                "paradigma.runtime.coding.atomic_replace_text",
                side_effect=failure,
            ):
                with self.assertRaises(CodingRuntimeStorageError):
                    store.update_task(changed, expected_source_hash=first.source_hash)

            self.assertEqual(before, first.path.read_bytes())
            self.assertFalse((first.path.parent / f".{first.path.name}.lock").exists())
            self.assertEqual(1, store.read_task("TASK-001").snapshot_revision)

    def test_existing_managed_lock_refuses_second_writer_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CodingRuntimeStore(Path(temporary) / "runtime")
            first = store.create_task(task())
            lock = first.path.parent / f".{first.path.name}.lock"
            lock.write_text("existing\n", encoding="utf-8")
            changed = replace(first.task, updated_at=NOW + timedelta(seconds=1))

            with self.assertRaisesRegex(Exception, "already being updated"):
                store.update_task(changed, expected_source_hash=first.source_hash)

            self.assertEqual(1, store.read_task("TASK-001").snapshot_revision)


if __name__ == "__main__":
    unittest.main()
