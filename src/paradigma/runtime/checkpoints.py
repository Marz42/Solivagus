"""Append-only YAML snapshots for CodingCheckpoint values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import re

import yaml

from ..atomic import atomic_create_text
from ..errors import AtomicWriteFailure
from ..integrations.coding import (
    BuildEvidence,
    CodingCheckpoint,
    EvidenceStatus,
    GitEvidence,
    TaskStatus,
    TestEvidence,
)
from ..parser import load_yaml_text, read_utf8_source
from .coding import (
    CODING_RUNTIME_SCHEMA_VERSION,
    CodingRuntimeConflictError,
    CodingRuntimeNotFoundError,
    CodingRuntimeSchemaError,
    CodingRuntimeStorageError,
)


_CHECKPOINT_ID = re.compile(r"^CHECKPOINT-[A-Z0-9][A-Z0-9_-]*$")


@dataclass(frozen=True)
class StoredCheckpointSnapshot:
    checkpoint: CodingCheckpoint
    snapshot_revision: int
    source_hash: str
    path: Path
    canonical: bool


def _exact(data: dict[str, Any], keys: tuple[str, ...], field: str) -> None:
    missing = [key for key in keys if key not in data]
    unknown = [key for key in data if key not in keys]
    if missing or unknown:
        raise CodingRuntimeSchemaError(
            f"{field} fields do not match schema (missing={missing}; unknown={unknown})"
        )


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CodingRuntimeSchemaError(f"{field} must be a string-keyed mapping")
    return value


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise CodingRuntimeSchemaError(f"{field} must be a string")
    return value


def _integer(value: object, field: str, *, optional: bool = False) -> int | None:
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodingRuntimeSchemaError(f"{field} must be an integer")
    return value


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodingRuntimeSchemaError(f"{field} must be a number or null")
    return float(value)


def _instant(value: object, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise CodingRuntimeSchemaError(f"{field} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CodingRuntimeSchemaError(f"{field} must include timezone")
    return parsed


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodingRuntimeSchemaError(f"{field} must be a list of strings")
    return tuple(value)


def _git_data(value: GitEvidence | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "repository_id": value.repository_id,
        "observed_at": value.observed_at.isoformat(),
        "head_commit": value.head_commit,
        "branch": value.branch,
        "dirty": value.dirty,
        "worktree_paths": list(value.worktree_paths),
    }


def _test_data(value: TestEvidence) -> dict[str, object]:
    return {
        "command": value.command,
        "status": value.status.value,
        "observed_at": value.observed_at.isoformat(),
        "exit_code": value.exit_code,
        "passed_count": value.passed_count,
        "failed_count": value.failed_count,
        "skipped_count": value.skipped_count,
        "duration_seconds": value.duration_seconds,
        "report_path": value.report_path,
        "output_hash": value.output_hash,
    }


def _build_data(value: BuildEvidence) -> dict[str, object]:
    return {
        "command": value.command,
        "status": value.status.value,
        "observed_at": value.observed_at.isoformat(),
        "exit_code": value.exit_code,
        "duration_seconds": value.duration_seconds,
        "artifact_paths": list(value.artifact_paths),
        "output_hash": value.output_hash,
    }


class CodingCheckpointCodec:
    """Strict deterministic checkpoint YAML codec."""

    def encode(self, checkpoint: CodingCheckpoint, snapshot_revision: int = 1) -> str:
        if snapshot_revision != 1:
            raise CodingRuntimeSchemaError("checkpoint snapshot_revision must be 1")
        data = {
            "coding_runtime_schema_version": CODING_RUNTIME_SCHEMA_VERSION,
            "kind": "coding_checkpoint",
            "snapshot_revision": 1,
            "checkpoint": {
                "checkpoint_id": checkpoint.checkpoint_id,
                "task_id": checkpoint.task_id,
                "session_id": checkpoint.session_id,
                "created_at": checkpoint.created_at.isoformat(),
                "task_status": checkpoint.task_status.value,
                "git": _git_data(checkpoint.git),
                "tests": [_test_data(item) for item in checkpoint.tests],
                "builds": [_build_data(item) for item in checkpoint.builds],
                "touched_paths": list(checkpoint.touched_paths),
                "narrative": {
                    "summary": checkpoint.summary,
                    "completed_work": list(checkpoint.completed_work),
                    "remaining_work": list(checkpoint.remaining_work),
                    "blockers": list(checkpoint.blockers),
                    "next_steps": list(checkpoint.next_steps),
                },
            },
        }
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )

    def decode(self, text: str, *, source: str = "<string>") -> tuple[CodingCheckpoint, int]:
        data = load_yaml_text(text, source=source)
        _exact(
            data,
            ("coding_runtime_schema_version", "kind", "snapshot_revision", "checkpoint"),
            "checkpoint snapshot",
        )
        if data["coding_runtime_schema_version"] != CODING_RUNTIME_SCHEMA_VERSION:
            raise CodingRuntimeSchemaError("unsupported coding_runtime_schema_version")
        if data["kind"] != "coding_checkpoint":
            raise CodingRuntimeSchemaError("kind must be 'coding_checkpoint'")
        if data["snapshot_revision"] != 1:
            raise CodingRuntimeSchemaError("checkpoint snapshot_revision must be 1")
        value = _mapping(data["checkpoint"], "checkpoint")
        _exact(
            value,
            (
                "checkpoint_id", "task_id", "session_id", "created_at", "task_status",
                "git", "tests", "builds", "touched_paths", "narrative",
            ),
            "checkpoint",
        )
        try:
            checkpoint = CodingCheckpoint(
                checkpoint_id=_text(value["checkpoint_id"], "checkpoint_id"),
                task_id=_text(value["task_id"], "task_id"),
                session_id=_text(value["session_id"], "session_id"),
                created_at=_instant(value["created_at"], "created_at"),
                task_status=_text(value["task_status"], "task_status"),
                git=self._git(value["git"]),
                tests=self._tests(value["tests"]),
                builds=self._builds(value["builds"]),
                touched_paths=_strings(value["touched_paths"], "touched_paths"),
                **self._narrative(value["narrative"]),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error
        return checkpoint, 1

    @staticmethod
    def _git(raw: object) -> GitEvidence | None:
        if raw is None:
            return None
        value = _mapping(raw, "git")
        _exact(
            value,
            ("repository_id", "observed_at", "head_commit", "branch", "dirty", "worktree_paths"),
            "git",
        )
        if not isinstance(value["dirty"], bool):
            raise CodingRuntimeSchemaError("git.dirty must be boolean")
        return GitEvidence(
            repository_id=_text(value["repository_id"], "git.repository_id"),
            observed_at=_instant(value["observed_at"], "git.observed_at"),
            head_commit=_text(value["head_commit"], "git.head_commit", optional=True),
            branch=_text(value["branch"], "git.branch", optional=True),
            dirty=value["dirty"],
            worktree_paths=_strings(value["worktree_paths"], "git.worktree_paths"),
        )

    @staticmethod
    def _tests(raw: object) -> tuple[TestEvidence, ...]:
        if not isinstance(raw, list):
            raise CodingRuntimeSchemaError("tests must be a list")
        result = []
        keys = (
            "command", "status", "observed_at", "exit_code", "passed_count",
            "failed_count", "skipped_count", "duration_seconds", "report_path", "output_hash",
        )
        for index, item in enumerate(raw):
            value = _mapping(item, f"tests[{index}]")
            _exact(value, keys, f"tests[{index}]")
            result.append(TestEvidence(
                command=_text(value["command"], "test.command"),
                status=_text(value["status"], "test.status"),
                observed_at=_instant(value["observed_at"], "test.observed_at"),
                exit_code=_integer(value["exit_code"], "test.exit_code", optional=True),
                passed_count=_integer(value["passed_count"], "test.passed_count", optional=True),
                failed_count=_integer(value["failed_count"], "test.failed_count", optional=True),
                skipped_count=_integer(value["skipped_count"], "test.skipped_count", optional=True),
                duration_seconds=_number(value["duration_seconds"], "test.duration_seconds"),
                report_path=_text(value["report_path"], "test.report_path", optional=True),
                output_hash=_text(value["output_hash"], "test.output_hash", optional=True),
            ))
        return tuple(result)

    @staticmethod
    def _builds(raw: object) -> tuple[BuildEvidence, ...]:
        if not isinstance(raw, list):
            raise CodingRuntimeSchemaError("builds must be a list")
        result = []
        keys = (
            "command", "status", "observed_at", "exit_code", "duration_seconds",
            "artifact_paths", "output_hash",
        )
        for index, item in enumerate(raw):
            value = _mapping(item, f"builds[{index}]")
            _exact(value, keys, f"builds[{index}]")
            result.append(BuildEvidence(
                command=_text(value["command"], "build.command"),
                status=_text(value["status"], "build.status"),
                observed_at=_instant(value["observed_at"], "build.observed_at"),
                exit_code=_integer(value["exit_code"], "build.exit_code", optional=True),
                duration_seconds=_number(value["duration_seconds"], "build.duration_seconds"),
                artifact_paths=_strings(value["artifact_paths"], "build.artifact_paths"),
                output_hash=_text(value["output_hash"], "build.output_hash", optional=True),
            ))
        return tuple(result)

    @staticmethod
    def _narrative(raw: object) -> dict[str, object]:
        value = _mapping(raw, "narrative")
        _exact(
            value,
            ("summary", "completed_work", "remaining_work", "blockers", "next_steps"),
            "narrative",
        )
        return {
            "summary": _text(value["summary"], "summary", optional=True),
            "completed_work": _strings(value["completed_work"], "completed_work"),
            "remaining_work": _strings(value["remaining_work"], "remaining_work"),
            "blockers": _strings(value["blockers"], "blockers"),
            "next_steps": _strings(value["next_steps"], "next_steps"),
        }


class CodingCheckpointStore:
    """Append-only checkpoint store; existing IDs are never overwritten."""

    def __init__(self, runtime_root: Path, *, codec: CodingCheckpointCodec | None = None):
        self.root = Path(runtime_root).resolve()
        self.codec = codec or CodingCheckpointCodec()

    @property
    def checkpoints_root(self) -> Path:
        return self.root / "checkpoints"

    def path_for(self, checkpoint_id: str) -> Path:
        if not isinstance(checkpoint_id, str) or not _CHECKPOINT_ID.fullmatch(checkpoint_id):
            raise CodingRuntimeSchemaError("checkpoint_id must use CHECKPOINT-... format")
        return self.checkpoints_root / f"{checkpoint_id}.yaml"

    def create(self, checkpoint: CodingCheckpoint) -> StoredCheckpointSnapshot:
        path = self.path_for(checkpoint.checkpoint_id)
        if path.is_symlink():
            raise CodingRuntimeStorageError(f"checkpoint must not be symlink: {path}")
        try:
            atomic_create_text(path, self.codec.encode(checkpoint))
        except FileExistsError as error:
            raise CodingRuntimeConflictError(f"checkpoint already exists: {path}") from error
        except AtomicWriteFailure as error:
            raise CodingRuntimeStorageError(str(error)) from error
        return self.read(checkpoint.checkpoint_id)

    def read(self, checkpoint_id: str) -> StoredCheckpointSnapshot:
        path = self.path_for(checkpoint_id)
        if not path.exists():
            raise CodingRuntimeNotFoundError(f"checkpoint does not exist: {path}")
        if path.is_symlink():
            raise CodingRuntimeStorageError(f"checkpoint must not be symlink: {path}")
        source = read_utf8_source(path)
        checkpoint, revision = self.codec.decode(source.text, source=str(path))
        if checkpoint.checkpoint_id != checkpoint_id:
            raise CodingRuntimeSchemaError("checkpoint_id does not match filename")
        encoded = self.codec.encode(checkpoint, revision).encode("utf-8")
        return StoredCheckpointSnapshot(
            checkpoint,
            revision,
            f"sha256:{hashlib.sha256(source.raw).hexdigest()}",
            path,
            source.raw == encoded,
        )
