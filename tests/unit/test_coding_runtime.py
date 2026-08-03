from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.errors import ParseFailure
from paradigma.integrations.coding import (
    CodingSession,
    CodingTask,
    RepositoryScope,
)
from paradigma.runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingRuntimeCodec,
    CodingRuntimeSchemaError,
)


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)


def repository() -> RepositoryScope:
    return RepositoryScope("workspace-1", "paradigma", ".", "https://example.test/repo.git")


def task(**changes) -> CodingTask:
    value = CodingTask(
        "TASK-001",
        repository(),
        "YAML runtime",
        "Make YAML the runtime source of truth.",
        "active",
        NOW,
        NOW,
    )
    return replace(value, **changes)


def session(**changes) -> CodingSession:
    value = CodingSession(
        "SESSION-001",
        "TASK-001",
        repository(),
        "active",
        NOW,
        NOW,
        agent_id="codex",
    )
    return replace(value, **changes)


class CodingRuntimeCodecTests(unittest.TestCase):
    def test_task_and_session_yaml_round_trip_is_deterministic(self) -> None:
        codec = CodingRuntimeCodec()
        task_yaml = codec.encode_task(task(), 3)
        decoded_task, task_revision = codec.decode_task(task_yaml)
        session_yaml = codec.encode_session(session(), 2)
        decoded_session, session_revision = codec.decode_session(session_yaml)

        self.assertEqual(task(), decoded_task)
        self.assertEqual(3, task_revision)
        self.assertEqual(task_yaml, codec.encode_task(decoded_task, task_revision))
        self.assertEqual(session(), decoded_session)
        self.assertEqual(2, session_revision)
        self.assertEqual(session_yaml, codec.encode_session(decoded_session, session_revision))
        self.assertIn('coding_runtime_schema_version: \'0.1\'', task_yaml)

    def test_pointer_round_trip_supports_explicit_empty_state(self) -> None:
        codec = CodingRuntimeCodec()
        task_pointer = ActiveTaskPointer(None, NOW)
        session_pointer = ActiveSessionPointer(None, None, NOW)

        self.assertEqual(
            task_pointer,
            codec.decode_active_task(codec.encode_active_task(task_pointer)),
        )
        self.assertEqual(
            session_pointer,
            codec.decode_active_session(codec.encode_active_session(session_pointer)),
        )

    def test_codec_rejects_unknown_missing_wrong_version_and_duplicate_keys(self) -> None:
        codec = CodingRuntimeCodec()
        valid = codec.encode_task(task(), 1)
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "unknown"):
            codec.decode_task(valid + "unexpected: true\n")
        with self.assertRaisesRegex(CodingRuntimeSchemaError, "unsupported"):
            codec.decode_task(valid.replace("'0.1'", "'9.9'", 1))
        with self.assertRaises(ParseFailure) as raised:
            codec.decode_task(valid + "kind: duplicate\n")
        self.assertEqual("YAML_DUPLICATE_KEY", raised.exception.code)

    def test_pointer_requires_paired_session_and_task_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "both"):
            ActiveSessionPointer("SESSION-001", None, NOW)
        with self.assertRaisesRegex(ValueError, "timezone"):
            ActiveTaskPointer(None, datetime(2026, 7, 24))


if __name__ == "__main__":
    unittest.main()
