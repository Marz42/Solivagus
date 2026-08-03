from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.errors import ParseFailure
from paradigma.kernel import (
    MemoryRecord,
    MemoryRelation,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    generate_memory_id,
)
from paradigma.storage.errors import MemoryDocumentError, MemoryIntegrityError
from paradigma.storage.markdown import MemoryMarkdownCodec


NOW = datetime(2026, 7, 24, 0, 0, tzinfo=timezone(timedelta(hours=8)))


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def record(**overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(1),
        "memory_type": MemoryType.DECISION,
        "title": "保留 Markdown canonical store",
        "content": "# Decision\n\nMarkdown remains readable.\n\n- one\n- two",
        "scope": MemoryScope(
            namespace="paradigma",
            workspace_id="workspace-1",
            project_id="project-1",
            entity_ids=("entity-a", "entity-b"),
        ),
        "provenance": (
            ProvenanceRef(
                source_type=ProvenanceType.USER_STATEMENT,
                source_id="conversation-1",
                observed_at=NOW,
                actor="user",
            ),
        ),
        "status": MemoryStatus.ACTIVE,
        "revision": 1,
        "valid_from": NOW,
        "valid_until": NOW + timedelta(days=30),
        "confidence": 0.95,
        "sensitivity": "internal",
        "tags": ("架构", "markdown"),
        "relations": (MemoryRelation("related_to", memory_id(2)),),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


class MemoryMarkdownCodecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.codec = MemoryMarkdownCodec()

    def test_round_trip_is_deterministic_and_preserves_unicode(self) -> None:
        original = record()
        encoded = self.codec.encode(original)
        decoded = self.codec.inspect(encoded, source="memory.md")

        self.assertEqual(original, decoded.record)
        self.assertEqual(encoded, self.codec.encode(decoded.record))
        self.assertTrue(decoded.canonical)
        self.assertTrue(decoded.content_hash.startswith("sha256:"))
        self.assertEqual(decoded.source_hash, self.codec.source_hash(encoded))
        self.assertIn("title: 保留 Markdown canonical store", encoded)
        self.assertTrue(encoded.endswith(f"{original.content}\n"))

    def test_encoder_matches_v0_1_golden_document(self) -> None:
        expected = (ROOT / "tests" / "golden" / "memory-record-v0.1.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(expected, self.codec.encode(record()))

    def test_content_hash_covers_metadata_and_body_but_not_yaml_formatting(self) -> None:
        original = record()
        original_hash = self.codec.content_hash(original)

        self.assertNotEqual(
            original_hash,
            self.codec.content_hash(replace(original, content="Changed")),
        )
        self.assertNotEqual(
            original_hash,
            self.codec.content_hash(
                replace(original, status=MemoryStatus.SUPERSEDED)
            ),
        )

        encoded = self.codec.encode(original)
        reformatted = encoded.replace(
            "title: 保留 Markdown canonical store",
            "title:  保留 Markdown canonical store",
        )
        inspected = self.codec.inspect(reformatted)
        self.assertEqual(original_hash, inspected.content_hash)
        self.assertFalse(inspected.canonical)
        self.assertNotEqual(self.codec.source_hash(encoded), inspected.source_hash)

    def test_hash_normalizes_equivalent_timezones_and_numeric_confidence(self) -> None:
        original = record(confidence=1)
        utc = timezone.utc
        source = original.provenance[0]
        equivalent = replace(
            original,
            confidence=1.0,
            provenance=(
                replace(source, observed_at=source.observed_at.astimezone(utc)),
            ),
            valid_from=original.valid_from.astimezone(utc),
            valid_until=original.valid_until.astimezone(utc),
            created_at=original.created_at.astimezone(utc),
            updated_at=original.updated_at.astimezone(utc),
        )
        self.assertEqual(
            self.codec.content_hash(original), self.codec.content_hash(equivalent)
        )

    def test_encoder_rejects_noncanonical_body_line_endings(self) -> None:
        with self.assertRaisesRegex(MemoryDocumentError, "LF line endings"):
            self.codec.encode(record(content="first\r\nsecond"))

    def test_tampered_body_is_detected_by_declared_content_hash(self) -> None:
        encoded = self.codec.encode(record())
        tampered = encoded.replace("Markdown remains readable.", "Changed by hand.")

        with self.assertRaises(MemoryIntegrityError) as raised:
            self.codec.decode(tampered, source="tampered.md")
        self.assertEqual("PD_MEMORY_INTEGRITY_ERROR", raised.exception.code)

    def test_schema_rejects_missing_unknown_and_wrong_version_fields(self) -> None:
        encoded = self.codec.encode(record())
        cases = (
            encoded.replace("revision: 1\n", ""),
            encoded.replace("content_hash:", "unknown: value\ncontent_hash:"),
            encoded.replace("memory_schema_version: '0.1'", "memory_schema_version: '9'"),
        )
        for text in cases:
            with self.subTest(text=text[:80]):
                with self.assertRaises(MemoryDocumentError) as raised:
                    self.codec.decode(text)
                self.assertEqual("PD_MEMORY_SCHEMA_ERROR", raised.exception.code)

    def test_invalid_nested_values_are_reported_as_schema_errors(self) -> None:
        encoded = self.codec.encode(record())
        invalid = encoded.replace(
            "observed_at: '2026-07-23T16:00:00.000000+00:00'",
            "observed_at: yesterday",
        )
        with self.assertRaises(MemoryDocumentError) as raised:
            self.codec.decode(invalid)
        self.assertEqual("PD_MEMORY_SCHEMA_ERROR", raised.exception.code)

    def test_shared_parser_diagnostics_are_not_reinterpreted(self) -> None:
        encoded = self.codec.encode(record())
        duplicated = encoded.replace("revision: 1", "revision: 1\nrevision: 2")
        with self.assertRaises(ParseFailure) as raised:
            self.codec.decode(duplicated, source="duplicate.md")
        self.assertEqual("YAML_DUPLICATE_KEY", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
