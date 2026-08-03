"""Strict YAML facts and rebuildable Markdown projections for Coding runtime state."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
import hashlib
import re

import yaml

from ..atomic import atomic_create_text, atomic_replace_text
from ..errors import AtomicWriteFailure, ParadigmaError
from ..integrations.coding import (
    CodingSession,
    CodingTask,
    RepositoryScope,
)
from ..parser import load_yaml_text, read_utf8_source


CODING_RUNTIME_SCHEMA_VERSION = "0.1"
_SOURCE_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_TASK_ID = re.compile(r"^TASK-[A-Z0-9][A-Z0-9_-]*$")
_SESSION_ID = re.compile(r"^SESSION-[A-Z0-9][A-Z0-9_-]*$")


class CodingRuntimeError(ParadigmaError, RuntimeError):
    code = "PD_CODING_RUNTIME_ERROR"


class CodingRuntimeSchemaError(CodingRuntimeError, ValueError):
    code = "PD_CODING_RUNTIME_SCHEMA_ERROR"


class CodingRuntimeConflictError(CodingRuntimeError):
    code = "PD_CODING_RUNTIME_CONFLICT"
    exit_code = 3


class CodingRuntimeNotFoundError(CodingRuntimeError, FileNotFoundError):
    code = "PD_CODING_RUNTIME_NOT_FOUND"


class CodingRuntimeStorageError(CodingRuntimeError, OSError):
    code = "PD_CODING_RUNTIME_STORAGE_ERROR"
    exit_code = 2


@dataclass(frozen=True)
class ActiveTaskPointer:
    task_id: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.task_id is not None and not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must use the TASK-... format or be None")
        _aware(self.updated_at, "updated_at")


@dataclass(frozen=True)
class ActiveSessionPointer:
    session_id: str | None
    task_id: str | None
    updated_at: datetime
    last_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.session_id is not None and not _SESSION_ID.fullmatch(self.session_id):
            raise ValueError("session_id must use the SESSION-... format or be None")
        if self.task_id is not None and not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must use the TASK-... format or be None")
        if self.last_session_id is not None and not _SESSION_ID.fullmatch(
            self.last_session_id
        ):
            raise ValueError("last_session_id must use the SESSION-... format or be None")
        if (self.session_id is None) != (self.task_id is None):
            raise ValueError("active session_id and task_id must both be set or both be None")
        _aware(self.updated_at, "updated_at")


@dataclass(frozen=True)
class StoredTaskSnapshot:
    task: CodingTask
    snapshot_revision: int
    source_hash: str
    path: Path
    canonical: bool


@dataclass(frozen=True)
class StoredSessionSnapshot:
    session: CodingSession
    snapshot_revision: int
    source_hash: str
    path: Path
    canonical: bool


@dataclass(frozen=True)
class StoredPointer:
    pointer: ActiveTaskPointer | ActiveSessionPointer
    source_hash: str
    path: Path
    canonical: bool


@dataclass(frozen=True)
class ProjectionStatus:
    active_task_current: bool
    handoff_current: bool

    @property
    def current(self) -> bool:
        return self.active_task_current and self.handoff_current


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CodingRuntimeSchemaError(f"{field} must be a string-keyed mapping")
    return value


def _exact(data: dict[str, Any], expected: tuple[str, ...], field: str) -> None:
    missing = [key for key in expected if key not in data]
    unknown = [key for key in data if key not in expected]
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        raise CodingRuntimeSchemaError(f"{field} fields do not match schema ({'; '.join(details)})")


def _string(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise CodingRuntimeSchemaError(f"{field} must be a string")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CodingRuntimeSchemaError(f"{field} must be an integer of at least 1")
    return value


def _datetime(value: object, field: str) -> datetime:
    text = _string(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise CodingRuntimeSchemaError(f"{field} must be an ISO 8601 datetime") from error
    try:
        return _aware(parsed, field)
    except ValueError as error:
        raise CodingRuntimeSchemaError(str(error)) from error


def _dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    )


def _repository_data(scope: RepositoryScope) -> dict[str, object]:
    return {
        "workspace_id": scope.workspace_id,
        "repository_id": scope.repository_id,
        "repository_path": scope.repository_path,
        "remote_url": scope.remote_url,
    }


def _repository(value: object) -> RepositoryScope:
    data = _mapping(value, "repository")
    expected = ("workspace_id", "repository_id", "repository_path", "remote_url")
    _exact(data, expected, "repository")
    try:
        return RepositoryScope(
            workspace_id=_string(data["workspace_id"], "repository.workspace_id"),
            repository_id=_string(data["repository_id"], "repository.repository_id"),
            repository_path=_string(data["repository_path"], "repository.repository_path"),
            remote_url=_string(data["remote_url"], "repository.remote_url", optional=True),
        )
    except ValueError as error:
        raise CodingRuntimeSchemaError(str(error)) from error


class CodingRuntimeCodec:
    """Deterministic strict codec for versioned Coding runtime YAML documents."""

    _TASK_FIELDS = (
        "task_id",
        "repository",
        "title",
        "goal",
        "status",
        "created_at",
        "updated_at",
        "status_reason",
        "parent_task_id",
    )
    _SESSION_FIELDS = (
        "session_id",
        "task_id",
        "repository",
        "status",
        "started_at",
        "updated_at",
        "ended_at",
        "agent_id",
        "current_checkpoint_id",
    )

    def encode_task(self, task: CodingTask, snapshot_revision: int) -> str:
        _integer(snapshot_revision, "snapshot_revision")
        return _dump(
            {
                "coding_runtime_schema_version": CODING_RUNTIME_SCHEMA_VERSION,
                "kind": "coding_task",
                "snapshot_revision": snapshot_revision,
                "task": {
                    "task_id": task.task_id,
                    "repository": _repository_data(task.repository),
                    "title": task.title,
                    "goal": task.goal,
                    "status": task.status.value,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                    "status_reason": task.status_reason,
                    "parent_task_id": task.parent_task_id,
                },
            }
        )

    def decode_task(self, text: str, *, source: str = "<string>") -> tuple[CodingTask, int]:
        data = load_yaml_text(text, source=source)
        _exact(data, ("coding_runtime_schema_version", "kind", "snapshot_revision", "task"), "task snapshot")
        self._header(data, "coding_task")
        revision = _integer(data["snapshot_revision"], "snapshot_revision")
        task = _mapping(data["task"], "task")
        _exact(task, self._TASK_FIELDS, "task")
        try:
            value = CodingTask(
                task_id=_string(task["task_id"], "task.task_id"),
                repository=_repository(task["repository"]),
                title=_string(task["title"], "task.title"),
                goal=_string(task["goal"], "task.goal"),
                status=_string(task["status"], "task.status"),
                created_at=_datetime(task["created_at"], "task.created_at"),
                updated_at=_datetime(task["updated_at"], "task.updated_at"),
                status_reason=_string(task["status_reason"], "task.status_reason", optional=True),
                parent_task_id=_string(task["parent_task_id"], "task.parent_task_id", optional=True),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error
        return value, revision

    def encode_session(self, session: CodingSession, snapshot_revision: int) -> str:
        _integer(snapshot_revision, "snapshot_revision")
        return _dump(
            {
                "coding_runtime_schema_version": CODING_RUNTIME_SCHEMA_VERSION,
                "kind": "coding_session",
                "snapshot_revision": snapshot_revision,
                "session": {
                    "session_id": session.session_id,
                    "task_id": session.task_id,
                    "repository": _repository_data(session.repository),
                    "status": session.status.value,
                    "started_at": session.started_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                    "agent_id": session.agent_id,
                    "current_checkpoint_id": session.current_checkpoint_id,
                },
            }
        )

    def decode_session(self, text: str, *, source: str = "<string>") -> tuple[CodingSession, int]:
        data = load_yaml_text(text, source=source)
        _exact(data, ("coding_runtime_schema_version", "kind", "snapshot_revision", "session"), "session snapshot")
        self._header(data, "coding_session")
        revision = _integer(data["snapshot_revision"], "snapshot_revision")
        session = _mapping(data["session"], "session")
        _exact(session, self._SESSION_FIELDS, "session")
        ended_raw = session["ended_at"]
        try:
            value = CodingSession(
                session_id=_string(session["session_id"], "session.session_id"),
                task_id=_string(session["task_id"], "session.task_id"),
                repository=_repository(session["repository"]),
                status=_string(session["status"], "session.status"),
                started_at=_datetime(session["started_at"], "session.started_at"),
                updated_at=_datetime(session["updated_at"], "session.updated_at"),
                ended_at=None if ended_raw is None else _datetime(ended_raw, "session.ended_at"),
                agent_id=_string(session["agent_id"], "session.agent_id", optional=True),
                current_checkpoint_id=_string(
                    session["current_checkpoint_id"],
                    "session.current_checkpoint_id",
                    optional=True,
                ),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error
        return value, revision

    def encode_active_task(self, pointer: ActiveTaskPointer) -> str:
        return _dump(
            {
                "coding_runtime_schema_version": CODING_RUNTIME_SCHEMA_VERSION,
                "kind": "active_task",
                "updated_at": pointer.updated_at.isoformat(),
                "task_id": pointer.task_id,
            }
        )

    def decode_active_task(self, text: str, *, source: str = "<string>") -> ActiveTaskPointer:
        data = load_yaml_text(text, source=source)
        _exact(data, ("coding_runtime_schema_version", "kind", "updated_at", "task_id"), "active task pointer")
        self._header(data, "active_task")
        try:
            return ActiveTaskPointer(
                _string(data["task_id"], "task_id", optional=True),
                _datetime(data["updated_at"], "updated_at"),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error

    def encode_active_session(self, pointer: ActiveSessionPointer) -> str:
        return _dump(
            {
                "coding_runtime_schema_version": CODING_RUNTIME_SCHEMA_VERSION,
                "kind": "active_session",
                "updated_at": pointer.updated_at.isoformat(),
                "session_id": pointer.session_id,
                "task_id": pointer.task_id,
                "last_session_id": pointer.last_session_id,
            }
        )

    def decode_active_session(self, text: str, *, source: str = "<string>") -> ActiveSessionPointer:
        data = load_yaml_text(text, source=source)
        _exact(
            data,
            (
                "coding_runtime_schema_version", "kind", "updated_at", "session_id",
                "task_id", "last_session_id",
            ),
            "active session pointer",
        )
        self._header(data, "active_session")
        try:
            return ActiveSessionPointer(
                _string(data["session_id"], "session_id", optional=True),
                _string(data["task_id"], "task_id", optional=True),
                _datetime(data["updated_at"], "updated_at"),
                _string(data["last_session_id"], "last_session_id", optional=True),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error

    @staticmethod
    def source_hash(raw: bytes) -> str:
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def _header(data: dict[str, Any], kind: str) -> None:
        if data.get("coding_runtime_schema_version") != CODING_RUNTIME_SCHEMA_VERSION:
            raise CodingRuntimeSchemaError("unsupported coding_runtime_schema_version")
        if data.get("kind") != kind:
            raise CodingRuntimeSchemaError(f"kind must be {kind!r}")


class CodingRuntimeStore:
    """CAS-protected YAML snapshots with Markdown projections derived from them."""

    def __init__(self, runtime_root: Path, *, codec: CodingRuntimeCodec | None = None):
        self.root = Path(runtime_root).resolve()
        self.codec = codec or CodingRuntimeCodec()

    @property
    def tasks_root(self) -> Path:
        return self.root / "tasks"

    @property
    def sessions_root(self) -> Path:
        return self.root / "sessions"

    def task_path(self, task_id: str) -> Path:
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise CodingRuntimeSchemaError("task_id must use the TASK-... format")
        return self.tasks_root / f"{task_id}.yaml"

    def session_path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise CodingRuntimeSchemaError("session_id must use the SESSION-... format")
        return self.sessions_root / f"{session_id}.yaml"

    def read_task(self, task_id: str) -> StoredTaskSnapshot:
        path = self.task_path(task_id)
        source = self._source(path)
        task, revision = self.codec.decode_task(source.text, source=str(path))
        if task.task_id != task_id:
            raise CodingRuntimeSchemaError("task_id does not match snapshot filename")
        canonical = source.raw == self.codec.encode_task(task, revision).encode("utf-8")
        return StoredTaskSnapshot(task, revision, self.codec.source_hash(source.raw), path, canonical)

    def create_task(self, task: CodingTask) -> StoredTaskSnapshot:
        path = self.task_path(task.task_id)
        self._create(path, self.codec.encode_task(task, 1))
        return self.read_task(task.task_id)

    def update_task(self, task: CodingTask, *, expected_source_hash: str) -> StoredTaskSnapshot:
        path = self.task_path(task.task_id)
        with self._exclusive(path):
            current = self.read_task(task.task_id)
            self._cas(current.source_hash, expected_source_hash)
            if task.created_at != current.task.created_at:
                raise CodingRuntimeConflictError("updated task must preserve created_at")
            if task.repository != current.task.repository:
                raise CodingRuntimeConflictError("updated task must preserve repository scope")
            if task.updated_at < current.task.updated_at:
                raise CodingRuntimeConflictError("updated_at must not be before stored task")
            self._replace(path, self.codec.encode_task(task, current.snapshot_revision + 1))
        return self.read_task(task.task_id)

    def read_session(self, session_id: str) -> StoredSessionSnapshot:
        path = self.session_path(session_id)
        source = self._source(path)
        session, revision = self.codec.decode_session(source.text, source=str(path))
        if session.session_id != session_id:
            raise CodingRuntimeSchemaError("session_id does not match snapshot filename")
        canonical = source.raw == self.codec.encode_session(session, revision).encode("utf-8")
        return StoredSessionSnapshot(
            session, revision, self.codec.source_hash(source.raw), path, canonical
        )

    def create_session(self, session: CodingSession) -> StoredSessionSnapshot:
        if not self.task_path(session.task_id).exists():
            raise CodingRuntimeNotFoundError(f"session task snapshot does not exist: {session.task_id}")
        task = self.read_task(session.task_id).task
        if session.repository != task.repository:
            raise CodingRuntimeConflictError("session repository must match its task")
        path = self.session_path(session.session_id)
        self._create(path, self.codec.encode_session(session, 1))
        return self.read_session(session.session_id)

    def update_session(
        self, session: CodingSession, *, expected_source_hash: str
    ) -> StoredSessionSnapshot:
        path = self.session_path(session.session_id)
        with self._exclusive(path):
            current = self.read_session(session.session_id)
            self._cas(current.source_hash, expected_source_hash)
            if session.task_id != current.session.task_id:
                raise CodingRuntimeConflictError("updated session must preserve task_id")
            if session.started_at != current.session.started_at:
                raise CodingRuntimeConflictError("updated session must preserve started_at")
            if session.repository != current.session.repository:
                raise CodingRuntimeConflictError("updated session must preserve repository scope")
            if session.updated_at < current.session.updated_at:
                raise CodingRuntimeConflictError("updated_at must not be before stored session")
            self._replace(
                path,
                self.codec.encode_session(session, current.snapshot_revision + 1),
            )
        return self.read_session(session.session_id)

    def read_active_task(self) -> StoredPointer:
        return self._read_pointer(self.root / "active-task.yaml", "task")

    def read_active_session(self) -> StoredPointer:
        return self._read_pointer(self.root / "active-session.yaml", "session")

    def set_active_task(
        self,
        pointer: ActiveTaskPointer,
        *,
        expected_source_hash: str | None,
    ) -> StoredPointer:
        if pointer.task_id is not None:
            self.read_task(pointer.task_id)
        session_pointer_path = self.root / "active-session.yaml"
        if session_pointer_path.exists():
            active_session = self.read_active_session().pointer
            assert isinstance(active_session, ActiveSessionPointer)
            if (
                active_session.session_id is not None
                and active_session.task_id != pointer.task_id
            ):
                raise CodingRuntimeConflictError(
                    "active session must be cleared before changing active task"
                )
        path = self.root / "active-task.yaml"
        self._write_pointer(path, self.codec.encode_active_task(pointer), expected_source_hash)
        return self.read_active_task()

    def set_active_session(
        self,
        pointer: ActiveSessionPointer,
        *,
        expected_source_hash: str | None,
    ) -> StoredPointer:
        if pointer.session_id is not None:
            session = self.read_session(pointer.session_id).session
            if session.task_id != pointer.task_id:
                raise CodingRuntimeConflictError("active session pointer task_id does not match session")
            active_task = self.read_active_task().pointer
            if not isinstance(active_task, ActiveTaskPointer) or active_task.task_id != pointer.task_id:
                raise CodingRuntimeConflictError("active session must belong to the active task")
        if pointer.last_session_id is not None:
            self.read_session(pointer.last_session_id)
        path = self.root / "active-session.yaml"
        self._write_pointer(path, self.codec.encode_active_session(pointer), expected_source_hash)
        return self.read_active_session()

    def expected_active_task_markdown(self) -> str:
        stored = self.read_active_task()
        pointer = stored.pointer
        assert isinstance(pointer, ActiveTaskPointer)
        task = self.read_task(pointer.task_id) if pointer.task_id else None
        return _render_active_task(pointer, task)

    def expected_handoff_markdown(self) -> str:
        stored = self.read_active_session()
        pointer = stored.pointer
        assert isinstance(pointer, ActiveSessionPointer)
        handoff_session_id = pointer.session_id or pointer.last_session_id
        session = self.read_session(handoff_session_id) if handoff_session_id else None
        task_id = pointer.task_id or (session.session.task_id if session else None)
        task = self.read_task(task_id) if task_id else None
        checkpoint = None
        if session is not None and session.session.current_checkpoint_id is not None:
            from .checkpoints import CodingCheckpointStore

            checkpoint = CodingCheckpointStore(self.root).read(
                session.session.current_checkpoint_id
            )
        return _render_handoff(pointer, session, task, checkpoint)

    def verify_projections(self) -> ProjectionStatus:
        active_path = self.root / "active-task.md"
        handoff_path = self.root / "handoff.md"
        return ProjectionStatus(
            active_task_current=(
                active_path.exists()
                and active_path.read_text(encoding="utf-8") == self.expected_active_task_markdown()
            ),
            handoff_current=(
                handoff_path.exists()
                and handoff_path.read_text(encoding="utf-8") == self.expected_handoff_markdown()
            ),
        )

    def rebuild_projections(self, *, dry_run: bool = False) -> ProjectionStatus:
        active = self.expected_active_task_markdown()
        handoff = self.expected_handoff_markdown()
        if not dry_run:
            self._replace(self.root / "active-task.md", active)
            self._replace(self.root / "handoff.md", handoff)
        return self.verify_projections() if not dry_run else ProjectionStatus(
            (self.root / "active-task.md").exists()
            and (self.root / "active-task.md").read_text(encoding="utf-8") == active,
            (self.root / "handoff.md").exists()
            and (self.root / "handoff.md").read_text(encoding="utf-8") == handoff,
        )

    def _read_pointer(self, path: Path, kind: str) -> StoredPointer:
        source = self._source(path)
        if kind == "task":
            pointer = self.codec.decode_active_task(source.text, source=str(path))
            encoded = self.codec.encode_active_task(pointer)
        else:
            pointer = self.codec.decode_active_session(source.text, source=str(path))
            encoded = self.codec.encode_active_session(pointer)
        return StoredPointer(
            pointer,
            self.codec.source_hash(source.raw),
            path,
            source.raw == encoded.encode("utf-8"),
        )

    def _write_pointer(self, path: Path, content: str, expected: str | None) -> None:
        with self._exclusive(path):
            if path.exists():
                current = self.codec.source_hash(self._source(path).raw)
                if expected is None:
                    raise CodingRuntimeConflictError("existing pointer requires expected_source_hash")
                self._cas(current, expected)
                self._replace(path, content)
            else:
                if expected is not None:
                    raise CodingRuntimeConflictError("missing pointer requires expected_source_hash=None")
                self._create(path, content)

    def _source(self, path: Path):
        if not path.exists():
            raise CodingRuntimeNotFoundError(f"runtime snapshot does not exist: {path}")
        if path.is_symlink():
            raise CodingRuntimeStorageError(f"runtime snapshot must not be a symlink: {path}")
        return read_utf8_source(path)

    @staticmethod
    def _cas(current: str, expected: str) -> None:
        if not isinstance(expected, str) or not _SOURCE_HASH.fullmatch(expected):
            raise CodingRuntimeConflictError("expected_source_hash must be a canonical sha256 digest")
        if current != expected:
            raise CodingRuntimeConflictError("runtime snapshot changed since it was read")

    @staticmethod
    def _create(path: Path, content: str) -> None:
        if path.is_symlink():
            raise CodingRuntimeStorageError(f"runtime snapshot must not be a symlink: {path}")
        try:
            atomic_create_text(path, content)
        except FileExistsError as error:
            raise CodingRuntimeConflictError(f"runtime snapshot already exists: {path}") from error
        except AtomicWriteFailure as error:
            raise CodingRuntimeStorageError(str(error)) from error

    @staticmethod
    def _replace(path: Path, content: str) -> None:
        if path.is_symlink():
            raise CodingRuntimeStorageError(f"runtime snapshot must not be a symlink: {path}")
        try:
            atomic_replace_text(path, content)
        except AtomicWriteFailure as error:
            raise CodingRuntimeStorageError(str(error)) from error

    @contextmanager
    def _exclusive(self, path: Path) -> Iterator[None]:
        lock = path.parent / f".{path.name}.lock"
        try:
            atomic_create_text(lock, f"target: {path.name}\n")
        except FileExistsError as error:
            raise CodingRuntimeConflictError(f"runtime snapshot is already being updated: {path}") from error
        except AtomicWriteFailure as error:
            raise CodingRuntimeStorageError(str(error)) from error
        try:
            yield
        finally:
            try:
                lock.unlink(missing_ok=True)
            except OSError as error:
                raise CodingRuntimeStorageError(f"failed to remove runtime lock {lock}: {error}") from error


def _render_active_task(
    pointer: ActiveTaskPointer, stored: StoredTaskSnapshot | None
) -> str:
    if stored is None:
        task_id = ""
        request = ""
        status = "pending"
        blockers = ""
        notes = "Generated from `active-task.yaml`; no active CodingTask."
    else:
        task = stored.task
        task_id = task.task_id
        request = f"{task.title}\n\n{task.goal}"
        status = task.status.value
        blockers = task.status_reason or ""
        notes = (
            "Generated from YAML facts; do not edit this projection by hand.\n\n"
            f"Snapshot revision: {stored.snapshot_revision}."
        )
    return f'''---
type: paradigma-runtime-state
title: Active Task
description: Rebuildable human projection of the active CodingTask YAML facts.
tags: [runtime, active-task, generated]
timestamp: {pointer.updated_at.isoformat()}
paradigma:
  layer: runtime
  temperature: hot
  lifecycle: ephemeral
  okf_export: false
  update_policy: generated
  source: /memory-bank/runtime/active-task.yaml
---

# Active Task

## Task ID

{task_id}

## User Request

{request}

## Current Status

{status}

## Checklist

## Relevant Knowledge

## Blockers

{blockers}

## Notes

{notes}
'''


def _render_handoff(
    pointer: ActiveSessionPointer,
    session: StoredSessionSnapshot | None,
    task: StoredTaskSnapshot | None,
    checkpoint=None,
) -> str:
    if session is None or task is None:
        body = "No active CodingSession."
    else:
        value = session.session
        body = f'''- Task: `{task.task.task_id}` — {task.task.title}
- Session: `{value.session_id}` ({value.status.value})
- Repository: `{value.repository.repository_id}`
- Agent: {value.agent_id or "unspecified"}
- Last checkpoint: `{value.current_checkpoint_id or "none"}`
'''
        if checkpoint is None:
            body += "\nNo checkpoint has been recorded."
        else:
            item = checkpoint.checkpoint
            body += f'''\n## Checkpoint

- Created: {item.created_at.isoformat()}
- Task status: {item.task_status.value}
- Git commit: `{item.git.head_commit if item.git and item.git.head_commit else "none"}`
- Touched paths: {", ".join(item.touched_paths) or "none"}
- Tests: {", ".join(test.status.value for test in item.tests) or "not recorded"}

## Summary

{item.summary or "No Agent summary."}

## Completed Work

{_markdown_items(item.completed_work)}

## Remaining Work

{_markdown_items(item.remaining_work)}

## Blockers

{_markdown_items(item.blockers)}

## Next Steps

{_markdown_items(item.next_steps)}'''
    return f'''---
type: paradigma-runtime-state
title: Coding Handoff
description: Rebuildable handoff projection of active CodingSession YAML facts.
tags: [runtime, handoff, generated]
timestamp: {pointer.updated_at.isoformat()}
paradigma:
  layer: runtime
  temperature: hot
  lifecycle: ephemeral
  okf_export: false
  update_policy: generated
  source: /memory-bank/runtime/active-session.yaml
---

# Handoff

{body}
'''


def _markdown_items(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "None."
