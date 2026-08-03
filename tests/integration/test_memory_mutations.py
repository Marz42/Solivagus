from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.application.memory import query_memories
from paradigma.application.mutations import (
    MemoryInputError,
    MemoryMutationError,
    commit_memory,
    forget_memory,
    propose_memory,
    revise_memory,
    supersede_memory,
    validate_memory,
)
from paradigma.cli.main import main
from paradigma.kernel import MemoryQuery, MemoryStatus, generate_memory_id
from paradigma.storage.catalog import CatalogQuery
from paradigma.storage.markdown import MarkdownMemoryStore


NOW = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)


def memory_id(seed: int) -> str:
    return generate_memory_id(NOW, randomness=seed.to_bytes(10, "big"))


def payload(title: str = "Lifecycle memory", content: str = "Initial body") -> dict:
    return {
        "memory_type": "semantic",
        "title": title,
        "content": content,
        "scope": {
            "namespace": "mutation-test",
            "project_id": "project-1",
            "entity_ids": ["entity-1"],
        },
        "provenance": [
            {
                "source_type": "user_statement",
                "source_id": "conversation-1",
                "observed_at": NOW.isoformat(),
                "actor": "user",
            }
        ],
        "validity": {"from": NOW.isoformat(), "until": None},
        "confidence": 1.0,
        "sensitivity": "internal",
        "tags": ["lifecycle"],
        "relations": [],
    }


def revision_payload(content: str) -> dict:
    return {
        "content": content,
        "provenance": [
            {
                "source_type": "user_statement",
                "source_id": "conversation-2",
                "observed_at": (NOW + timedelta(seconds=2)).isoformat(),
                "actor": "user",
            }
        ],
    }


class MemoryMutationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = self.root / ".paradigma" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: memory-bank/memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        self.store = MarkdownMemoryStore(self.root / "memory-bank" / "memories")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_propose_commit_query_revise_supersede_forget_full_chain(self) -> None:
        identifier = memory_id(1)
        preview = propose_memory(
            self.root,
            payload(),
            memory_id=identifier,
            at=NOW,
        )
        self.assertFalse(preview.written)
        self.assertFalse(preview.path.exists())

        proposed = propose_memory(
            self.root,
            payload(),
            write=True,
            memory_id=identifier,
            at=NOW,
        )
        self.assertEqual(MemoryStatus.CANDIDATE, proposed.record.status)
        self.assertEqual(1, proposed.record.revision)
        self.assertTrue(proposed.catalog_refreshed)
        self.assertEqual((), query_memories(self.root, CatalogQuery()))

        validated = validate_memory(self.root, identifier).stored
        committed = commit_memory(
            self.root,
            identifier,
            expected_source_hash=validated.source_hash,
            write=True,
            at=NOW + timedelta(seconds=1),
        )
        self.assertEqual(MemoryStatus.ACTIVE, committed.record.status)
        self.assertEqual(2, committed.record.revision)
        results = query_memories(
            self.root,
            CatalogQuery(MemoryQuery(memory_ids=(identifier,))),
        )
        self.assertEqual(identifier, results[0].record.memory_id)

        revised = revise_memory(
            self.root,
            identifier,
            revision_payload("Revised searchable body"),
            expected_source_hash=committed.source_hash,
            write=True,
            at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(3, revised.record.revision)
        self.assertEqual("Revised searchable body", revised.record.content)
        self.assertEqual(
            identifier,
            query_memories(
                self.root,
                CatalogQuery(MemoryQuery(text="Revised")),
            )[0].record.memory_id,
        )

        replacement_id = memory_id(2)
        replacement = propose_memory(
            self.root,
            payload("Replacement", "New truth"),
            write=True,
            memory_id=replacement_id,
            at=NOW,
        )
        replacement = commit_memory(
            self.root,
            replacement_id,
            expected_source_hash=replacement.source_hash,
            write=True,
            at=NOW + timedelta(seconds=1),
        )
        superseded = supersede_memory(
            self.root,
            identifier,
            replacement_id,
            expected_source_hash=revised.source_hash,
            write=True,
            at=NOW + timedelta(seconds=3),
        )
        self.assertEqual(MemoryStatus.SUPERSEDED, superseded.record.status)
        self.assertEqual("superseded_by", superseded.record.relations[-1].relation_type)
        active_ids = [
            result.record.memory_id
            for result in query_memories(self.root, CatalogQuery())
        ]
        self.assertEqual([replacement_id], active_ids)

        forgotten = forget_memory(
            self.root,
            replacement_id,
            expected_source_hash=replacement.source_hash,
            write=True,
            at=NOW + timedelta(seconds=4),
        )
        self.assertEqual(MemoryStatus.TOMBSTONED, forgotten.record.status)
        self.assertTrue(forgotten.path.exists(), "forget must not physically purge")
        self.assertEqual((), query_memories(self.root, CatalogQuery()))

    def test_dry_run_and_stale_source_hash_never_mutate(self) -> None:
        proposed = propose_memory(
            self.root,
            payload(),
            write=True,
            memory_id=memory_id(1),
            at=NOW,
        )
        before = proposed.path.read_bytes()
        preview = commit_memory(
            self.root,
            proposed.record.memory_id,
            expected_source_hash=proposed.source_hash,
            at=NOW + timedelta(seconds=1),
        )
        self.assertFalse(preview.written)
        self.assertEqual(before, proposed.path.read_bytes())
        with self.assertRaisesRegex(MemoryMutationError, "changed since validation"):
            commit_memory(
                self.root,
                proposed.record.memory_id,
                expected_source_hash="sha256:" + "0" * 64,
                write=True,
                at=NOW + timedelta(seconds=1),
            )
        self.assertEqual(before, proposed.path.read_bytes())

    def test_payload_and_transition_policy_reject_ambiguous_mutations(self) -> None:
        invalid = payload()
        invalid["unknown"] = True
        with self.assertRaisesRegex(MemoryInputError, "unknown"):
            propose_memory(self.root, invalid, memory_id=memory_id(1), at=NOW)
        nested = payload()
        nested["scope"]["unknown"] = "value"
        with self.assertRaisesRegex(MemoryInputError, "scope fields invalid"):
            propose_memory(self.root, nested, memory_id=memory_id(1), at=NOW)

        proposed = propose_memory(
            self.root,
            payload(),
            write=True,
            memory_id=memory_id(1),
            at=NOW,
        )
        with self.assertRaisesRegex(MemoryInputError, "provide provenance"):
            revise_memory(
                self.root,
                proposed.record.memory_id,
                {"content": "no source"},
                expected_source_hash=proposed.source_hash,
                at=NOW + timedelta(seconds=1),
            )
        with self.assertRaisesRegex(MemoryMutationError, "replacement memory must be active"):
            supersede_memory(
                self.root,
                proposed.record.memory_id,
                proposed.record.memory_id,
                expected_source_hash=proposed.source_hash,
                at=NOW + timedelta(seconds=1),
            )


class MemoryMutationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        config = self.root / ".paradigma" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: memory-bank/memories
catalog_path: .paradigma/cache/catalog.sqlite3
""",
            encoding="utf-8",
        )
        self.input = self.root / "proposal.yaml"
        self.input.write_text(
            yaml.safe_dump(payload(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [*arguments, "--project", str(self.root), "--format", "json"]
            )
        return exit_code, json.loads(output.getvalue())

    def test_cli_propose_validate_commit_and_default_dry_run(self) -> None:
        identifier = memory_id(7)
        preview_exit, preview = self.run_cli(
            "memory",
            "propose",
            "--input",
            str(self.input),
            "--memory-id",
            identifier,
        )
        self.assertEqual(0, preview_exit)
        self.assertTrue(preview["dry_run"])
        self.assertFalse((self.root / "memory-bank/memories" / f"{identifier}.md").exists())

        write_exit, written = self.run_cli(
            "memory",
            "propose",
            "--input",
            str(self.input),
            "--memory-id",
            identifier,
            "--write",
        )
        self.assertEqual(0, write_exit)
        self.assertEqual("candidate", written["data"]["status"])
        validate_exit, validated = self.run_cli("memory", "validate", identifier)
        self.assertEqual(0, validate_exit)
        source_hash = validated["data"]["source_hash"]

        commit_exit, committed = self.run_cli(
            "memory",
            "commit",
            identifier,
            "--expected-source-hash",
            source_hash,
            "--write",
        )
        self.assertEqual(0, commit_exit)
        self.assertEqual("active", committed["data"]["status"])
        self.assertEqual(2, committed["data"]["revision"])
        self.assertTrue(committed["data"]["catalog_refreshed"])

        revision = self.root / "revision.yaml"
        revision.write_text(
            yaml.safe_dump(revision_payload("CLI revision"), sort_keys=False),
            encoding="utf-8",
        )
        revise_exit, revised = self.run_cli(
            "memory",
            "revise",
            identifier,
            "--input",
            str(revision),
            "--expected-source-hash",
            committed["data"]["source_hash"],
            "--write",
        )
        self.assertEqual(0, revise_exit)
        self.assertEqual(3, revised["data"]["revision"])

        replacement_id = memory_id(8)
        _, replacement = self.run_cli(
            "memory",
            "propose",
            "--input",
            str(self.input),
            "--memory-id",
            replacement_id,
            "--write",
        )
        _, replacement = self.run_cli(
            "memory",
            "commit",
            replacement_id,
            "--expected-source-hash",
            replacement["data"]["source_hash"],
            "--write",
        )
        supersede_exit, superseded = self.run_cli(
            "memory",
            "supersede",
            identifier,
            "--replacement-id",
            replacement_id,
            "--expected-source-hash",
            revised["data"]["source_hash"],
            "--write",
        )
        self.assertEqual(0, supersede_exit)
        self.assertEqual("superseded", superseded["data"]["status"])

        forget_exit, forgotten = self.run_cli(
            "memory",
            "forget",
            replacement_id,
            "--expected-source-hash",
            replacement["data"]["source_hash"],
            "--write",
        )
        self.assertEqual(0, forget_exit)
        self.assertEqual("tombstoned", forgotten["data"]["status"])


if __name__ == "__main__":
    unittest.main()
