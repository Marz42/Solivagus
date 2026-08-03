from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.integrations.coding import (
    BuildEvidence,
    CodingCheckpoint,
    GitEvidence,
    TestEvidence,
)
from paradigma.runtime import (
    CodingCheckpointCodec,
    CodingCheckpointStore,
    CodingRuntimeConflictError,
    CodingRuntimeSchemaError,
    CodingRuntimeStorageError,
)
from paradigma.errors import AtomicWriteFailure
from unittest import mock


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64


def checkpoint() -> CodingCheckpoint:
    return CodingCheckpoint(
        "CHECKPOINT-001",
        "TASK-001",
        "SESSION-001",
        NOW,
        "active",
        git=GitEvidence("paradigma", NOW, "b" * 40, "main", True, ("src/a.py",)),
        tests=(TestEvidence("python -m unittest", "passed", NOW, exit_code=0, output_hash=DIGEST),),
        builds=(BuildEvidence("python -m build", "passed", NOW, exit_code=0, output_hash=DIGEST),),
        touched_paths=("src/a.py",),
        summary="Checkpoint summary",
        completed_work=("Implemented codec",),
        remaining_work=("Implement CLI",),
        next_steps=("Run tests",),
    )


class CodingCheckpointRuntimeTests(unittest.TestCase):
    def test_checkpoint_round_trip_is_deterministic_and_complete(self) -> None:
        codec = CodingCheckpointCodec()
        encoded = codec.encode(checkpoint())
        decoded, revision = codec.decode(encoded)
        self.assertEqual(checkpoint(), decoded)
        self.assertEqual(1, revision)
        self.assertEqual(encoded, codec.encode(decoded, revision))
        self.assertIn("Checkpoint summary", encoded)

    def test_checkpoint_schema_is_exact_and_append_only(self) -> None:
        codec = CodingCheckpointCodec()
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "unknown"):
            codec.decode(codec.encode(checkpoint()) + "unknown: true\n")
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "must be 1"):
            codec.encode(checkpoint(), 2)

        with tempfile.TemporaryDirectory() as temporary:
            store = CodingCheckpointStore(Path(temporary))
            first = store.create(checkpoint())
            self.assertTrue(first.canonical)
            with self.assertRaises(CodingRuntimeConflictError):
                store.create(checkpoint())
            self.assertEqual(first, store.read("CHECKPOINT-001"))

    def test_atomic_create_failure_leaves_no_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CodingCheckpointStore(Path(temporary))
            with mock.patch(
                "paradigma.runtime.checkpoints.atomic_create_text",
                side_effect=AtomicWriteFailure(
                    store.path_for("CHECKPOINT-001"), "atomic create", OSError("injected")
                ),
            ):
                with self.assertRaisesRegex(CodingRuntimeStorageError, "injected"):
                    store.create(checkpoint())
            self.assertFalse(store.path_for("CHECKPOINT-001").exists())


if __name__ == "__main__":
    unittest.main()
