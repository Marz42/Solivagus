from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.integrations.coding import (
    ContextDocument,
    ContextExclusion,
    ContextPriority,
    ContextRequest,
    ContextSourceKind,
)
from paradigma.runtime import (
    CodingContextManifestCodec,
    CodingContextManifestStore,
    CodingRuntimeSchemaError,
)


DIGEST = "sha256:" + "a" * 64


def manifest():
    codec = CodingContextManifestCodec()
    return codec.create(
        request=ContextRequest(
            "Implement Context Builder",
            "TASK-001",
            explicit_paths=("src/paradigma",),
            explicit_symbols=("ContextRequest",),
            keywords=("manifest",),
            budget_tokens=12000,
        ),
        session_id="SESSION-001",
        checkpoint_id="CHECKPOINT-001",
        source_digest=DIGEST,
        documents=(
            ContextDocument(
                "memory-bank/knowledge/architecture.md",
                "memory-bank/knowledge/architecture.md",
                ContextSourceKind.KNOWLEDGE,
                "System Architecture",
                ContextPriority.REQUIRED,
                321,
                ("mandatory_hot_document", "symbol_match:ContextRequest"),
            ),
        ),
        excluded=(
            ContextExclusion(
                "MEM-01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "memory-bank/memories/MEM-01ARZ3NDEKTSV4RRFFQ69G5FAV.md",
                "budget_trimmed",
                900,
            ),
        ),
        warnings=(),
    )


class CodingContextValueAndCodecTests(unittest.TestCase):
    def test_request_accepts_mandatory_only_and_rejects_ambiguous_values(self) -> None:
        self.assertEqual(10, ContextRequest("Resume task", "TASK-001", budget_tokens=10).budget_tokens)
        with self.assertRaisesRegex(ValueError, "POSIX"):
            ContextRequest("Task", "TASK-001", explicit_paths=("src\\bad.py",))
        with self.assertRaisesRegex(ValueError, "canonical"):
            ContextRequest("Task", "TASK-001", explicit_paths=("C:/bad.py",))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            ContextRequest("Task", "TASK-001", keywords=("same", "same"))
        with self.assertRaisesRegex(ValueError, "between"):
            ContextRequest("Task", "TASK-001", budget_tokens=0)

    def test_manifest_codec_matches_golden_and_rejects_tampering(self) -> None:
        codec = CodingContextManifestCodec()
        encoded = codec.encode(manifest())
        golden = (ROOT / "tests" / "golden" / "coding-context-manifest.yaml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(golden, encoded)
        self.assertEqual(manifest(), codec.decode(encoded))
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "checksum"):
            codec.decode(encoded.replace("estimated_tokens: 321", "estimated_tokens: 322"))
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "unknown"):
            codec.decode(encoded + "unknown: true\n")

    def test_manifest_store_is_canonical_and_atomic_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CodingContextManifestStore(Path(temporary))
            first = store.write(manifest())
            second = store.read()
            self.assertEqual(first, second)
            self.assertTrue(second.canonical)
            self.assertEqual(manifest().checksum, second.manifest.checksum)


if __name__ == "__main__":
    unittest.main()
