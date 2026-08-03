from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.kernel import (
    MemoryQuery,
    MemoryRecord,
    MemoryRelation,
    MemoryResult,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProvenanceRef,
    ProvenanceType,
    MemoryTransitionError,
    commit_candidate,
    forget_record,
    generate_memory_id,
    is_memory_id,
    revise_record,
    supersede_record,
)


NOW = datetime(2026, 7, 23, 16, 0, tzinfo=timezone.utc)


def memory_id(seed: int = 1, *, instant: datetime = NOW) -> str:
    return generate_memory_id(instant, randomness=seed.to_bytes(10, "big"))


def provenance(
    source_type: ProvenanceType | str = ProvenanceType.USER_STATEMENT,
) -> ProvenanceRef:
    return ProvenanceRef(
        source_type=source_type,
        source_id="conversation-1",
        observed_at=NOW,
        actor="user",
    )


def record(**overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": memory_id(),
        "memory_type": MemoryType.SEMANTIC,
        "title": "Package boundary",
        "content": "The kernel is independent from storage adapters.",
        "scope": MemoryScope(namespace="paradigma", project_id="project-1"),
        "provenance": (provenance(),),
        "status": MemoryStatus.ACTIVE,
        "revision": 1,
        "valid_from": NOW,
        "valid_until": None,
        "confidence": 1.0,
        "sensitivity": "internal",
        "tags": ("architecture", "kernel"),
        "relations": (),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)  # type: ignore[arg-type]


class MemoryIdentifierTests(unittest.TestCase):
    def test_identifier_is_canonical_reproducible_and_time_sortable(self) -> None:
        first = generate_memory_id(NOW, randomness=b"\x00" * 10)
        same = generate_memory_id(NOW, randomness=b"\x00" * 10)
        later = generate_memory_id(
            NOW + timedelta(milliseconds=1), randomness=b"\x00" * 10
        )

        self.assertEqual(first, same)
        self.assertEqual(30, len(first))
        self.assertTrue(is_memory_id(first))
        self.assertLess(first, later)
        self.assertFalse(is_memory_id(first.lower()))
        self.assertFalse(is_memory_id("MEM-01I00000000000000000000000"))

    def test_identifier_rejects_ambiguous_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            generate_memory_id(NOW.replace(tzinfo=None), randomness=b"\x00" * 10)
        with self.assertRaisesRegex(ValueError, "exactly 10 bytes"):
            generate_memory_id(NOW, randomness=b"short")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            generate_memory_id(0, randomness=b"\x00" * 10)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "48-bit"):
            generate_memory_id(
                datetime(1969, 12, 31, tzinfo=timezone.utc),
                randomness=b"\x00" * 10,
            )


class MemoryValueTests(unittest.TestCase):
    def test_scope_and_provenance_are_validated_and_immutable(self) -> None:
        scope = MemoryScope(
            namespace="shared",
            workspace_id="workspace-1",
            entity_ids=("entity-1",),
        )
        source = provenance("user_statement")

        self.assertEqual(ProvenanceType.USER_STATEMENT, source.source_type)
        with self.assertRaises(FrozenInstanceError):
            scope.namespace = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            MemoryScope(namespace="shared", entity_ids=("one", "one"))
        with self.assertRaisesRegex(ValueError, "identify"):
            ProvenanceRef(source_type=ProvenanceType.MANUAL_ENTRY)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            ProvenanceRef(
                source_type=ProvenanceType.WEB_SOURCE,
                source_uri="https://example.test",
                excerpt_hash="not-a-hash",
            )

    def test_record_accepts_string_enums_and_exposes_inclusive_validity(self) -> None:
        item = record(memory_type="decision", status="active")

        self.assertEqual(MemoryType.DECISION, item.memory_type)
        self.assertEqual(MemoryStatus.ACTIVE, item.status)
        self.assertTrue(item.is_valid_at(NOW))
        self.assertTrue(item.is_valid_at(NOW + timedelta(days=10)))
        with self.assertRaises(FrozenInstanceError):
            item.revision = 2  # type: ignore[misc]

    def test_record_rejects_invalid_revision_time_and_confidence(self) -> None:
        invalid_cases = (
            ({"revision": 0}, "at least 1"),
            (
                {"updated_at": NOW - timedelta(seconds=1)},
                "before created_at",
            ),
            (
                {
                    "valid_from": NOW,
                    "valid_until": NOW - timedelta(seconds=1),
                },
                "before valid_from",
            ),
            ({"confidence": float("nan")}, "between 0 and 1"),
            ({"created_at": NOW.replace(tzinfo=None)}, "timezone-aware"),
            ({"provenance": ()}, "at least one source"),
        )
        for changes, message in invalid_cases:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, message):
                    record(**changes)

    def test_agent_inference_requires_confidence(self) -> None:
        inferred = provenance(ProvenanceType.AGENT_INFERENCE)
        with self.assertRaisesRegex(ValueError, "requires confidence"):
            record(provenance=(inferred,), confidence=None)

    def test_relation_rejects_self_links_and_duplicates(self) -> None:
        related = MemoryRelation("related_to", memory_id(2))
        self.assertEqual("related_to", related.relation_type)
        with self.assertRaisesRegex(ValueError, "relate to itself"):
            record(relations=(MemoryRelation("related_to", memory_id()),))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            record(relations=(related, related))
        with self.assertRaisesRegex(ValueError, "snake_case"):
            MemoryRelation("Related To", memory_id(2))


class MemoryQueryAndResultTests(unittest.TestCase):
    def test_ordinary_query_defaults_to_active_only(self) -> None:
        query = MemoryQuery(text="kernel")

        self.assertEqual((MemoryStatus.ACTIVE,), query.statuses)
        self.assertFalse(query.include_related)
        self.assertEqual(50, query.limit)

    def test_query_validates_filters_and_relation_expansion(self) -> None:
        query = MemoryQuery(
            memory_ids=(memory_id(),),
            statuses=("candidate", "active"),
            include_related=True,
            relation_types=("related_to",),
            valid_at=NOW,
            limit=100,
        )
        self.assertEqual(
            (MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE), query.statuses
        )

        with self.assertRaisesRegex(ValueError, "include_related"):
            MemoryQuery(relation_types=("related_to",))
        with self.assertRaisesRegex(ValueError, "between 1 and 1000"):
            MemoryQuery(limit=0)
        with self.assertRaisesRegex(ValueError, "at least one status"):
            MemoryQuery(statuses=())

    def test_result_carries_explanation_without_copying_record_fields(self) -> None:
        item = record()
        source_id = memory_id(2)
        result = MemoryResult(
            record=item,
            score=0.75,
            matched_fields=("title", "tags"),
            match_reasons=("keyword:kernel",),
            relation_source_id=source_id,
            warnings=("validity not evaluated",),
        )

        self.assertIs(item, result.record)
        self.assertEqual(source_id, result.relation_source_id)
        with self.assertRaisesRegex(ValueError, "another memory"):
            MemoryResult(record=item, relation_source_id=item.memory_id)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            MemoryResult(record=item, score=-0.1)


class MemoryTransitionTests(unittest.TestCase):
    def test_candidate_commit_and_revision_increment_are_pure(self) -> None:
        candidate = record(status=MemoryStatus.CANDIDATE)
        active = commit_candidate(candidate, at=NOW + timedelta(seconds=1))

        self.assertEqual(MemoryStatus.CANDIDATE, candidate.status)
        self.assertEqual(MemoryStatus.ACTIVE, active.status)
        self.assertEqual(2, active.revision)
        revised = revise_record(
            active,
            changes={
                "content": "Revised content.",
                "provenance": (provenance(),),
            },
            at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(3, revised.revision)
        self.assertEqual("Revised content.", revised.content)

    def test_supersede_and_forget_have_explicit_terminal_semantics(self) -> None:
        active = record()
        replacement_id = memory_id(2)
        superseded = supersede_record(
            active,
            replacement_id=replacement_id,
            at=NOW + timedelta(seconds=1),
        )
        self.assertEqual(MemoryStatus.SUPERSEDED, superseded.status)
        self.assertEqual(
            (MemoryRelation("superseded_by", replacement_id),),
            superseded.relations,
        )
        tombstoned = forget_record(
            superseded, at=NOW + timedelta(seconds=2)
        )
        self.assertEqual(MemoryStatus.TOMBSTONED, tombstoned.status)
        self.assertEqual(3, tombstoned.revision)

    def test_invalid_transitions_and_revision_provenance_are_rejected(self) -> None:
        active = record()
        with self.assertRaisesRegex(MemoryTransitionError, "requires status candidate"):
            commit_candidate(active, at=NOW + timedelta(seconds=1))
        with self.assertRaisesRegex(MemoryTransitionError, "provide provenance"):
            revise_record(
                active,
                changes={"content": "missing source"},
                at=NOW + timedelta(seconds=1),
            )
        with self.assertRaisesRegex(MemoryTransitionError, "must not precede"):
            forget_record(active, at=NOW - timedelta(seconds=1))
        forgotten = forget_record(active, at=NOW + timedelta(seconds=1))
        with self.assertRaisesRegex(MemoryTransitionError, "already tombstoned"):
            forget_record(forgotten, at=NOW + timedelta(seconds=2))


if __name__ == "__main__":
    unittest.main()
