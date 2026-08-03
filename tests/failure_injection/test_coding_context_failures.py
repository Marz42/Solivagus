from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.errors import AtomicWriteFailure
from paradigma.integrations.coding import (
    ContextDocument,
    ContextPriority,
    ContextRequest,
    ContextSourceKind,
)
from paradigma.runtime import (
    CodingContextManifestCodec,
    CodingContextManifestStore,
    CodingRuntimeStorageError,
)


DIGEST = "sha256:" + "a" * 64


def value(intent: str):
    return CodingContextManifestCodec().create(
        request=ContextRequest(intent, "TASK-001"),
        session_id=None,
        checkpoint_id=None,
        source_digest=DIGEST,
        documents=(
            ContextDocument(
                "architecture",
                "memory-bank/knowledge/architecture.md",
                ContextSourceKind.KNOWLEDGE,
                "Architecture",
                ContextPriority.REQUIRED,
                10,
                ("mandatory_hot_document",),
            ),
        ),
        excluded=(),
        warnings=(),
    )


class CodingContextFailureTests(unittest.TestCase):
    def test_atomic_replace_failure_preserves_previous_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CodingContextManifestStore(Path(temporary))
            first = store.write(value("First request"))
            original = first.path.read_bytes()
            failure = AtomicWriteFailure(
                first.path, "atomic replace", OSError("injected")
            )
            with mock.patch(
                "paradigma.runtime.context.atomic_replace_text",
                side_effect=failure,
            ):
                with self.assertRaisesRegex(CodingRuntimeStorageError, "injected"):
                    store.write(value("Second request"))
            self.assertEqual(original, first.path.read_bytes())
            self.assertEqual(value("First request"), store.read().manifest)


if __name__ == "__main__":
    unittest.main()
