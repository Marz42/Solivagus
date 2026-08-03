"""Application outcomes for Coding YAML runtime projections."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import require_valid_config
from ..diagnostics import Diagnostic
from ..runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingRuntimeSchemaError,
    CodingRuntimeStore,
)
from .outcomes import CommandOutcome


def coding_runtime_verify_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    config = require_valid_config(repository_root)
    store = CodingRuntimeStore(
        config.repository_root / config.runtime_root_name
    )
    status = store.verify_projections()
    diagnostics = () if status.current else (
        Diagnostic(
            "PD_CODING_RUNTIME_PROJECTION_STALE",
            "Coding runtime Markdown projections do not match YAML facts; run `pd runtime rebuild`",
            config.runtime_root_name,
        ),
    )
    return CommandOutcome(
        command="runtime verify",
        data={
            "current": status.current,
            "active_task_current": status.active_task_current,
            "handoff_current": status.handoff_current,
        },
        messages=(
            "Coding runtime projections match YAML facts."
            if status.current
            else "Coding runtime projections are stale."
        ,),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )


def coding_runtime_rebuild_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    config = require_valid_config(repository_root)
    store = CodingRuntimeStore(
        config.repository_root / config.runtime_root_name
    )
    before = store.verify_projections()
    after = store.rebuild_projections(dry_run=dry_run)
    return CommandOutcome(
        command="runtime rebuild",
        data={
            "current_before": before.current,
            "current_after": after.current if not dry_run else before.current,
            "would_change": not before.current,
            "written": not dry_run,
        },
        messages=(
            "Coding runtime projections validated; dry-run made no changes."
            if dry_run
            else "Coding runtime Markdown projections rebuilt from YAML facts."
        ,),
        changed=(not dry_run and not before.current),
        dry_run=dry_run,
    )


def coding_runtime_init_outcome(
    repository_root: Path,
    *,
    write: bool = False,
    at: datetime | None = None,
) -> CommandOutcome:
    """Initialize missing null pointers and projections without overwriting facts."""

    config = require_valid_config(repository_root)
    instant = at or datetime.now().astimezone()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise CodingRuntimeSchemaError(
            "runtime initialization time must be timezone-aware"
        )
    store = CodingRuntimeStore(config.repository_root / config.runtime_root_name)
    task_missing = not (store.root / "active-task.yaml").exists()
    session_missing = not (store.root / "active-session.yaml").exists()
    projection_stale = False
    if not task_missing:
        store.read_active_task()
    if not session_missing:
        store.read_active_session()
    if not task_missing and not session_missing:
        projection_stale = not store.verify_projections().current
    would_change = task_missing or session_missing or projection_stale
    if write:
        if task_missing:
            store.set_active_task(
                ActiveTaskPointer(None, instant), expected_source_hash=None
            )
        if session_missing:
            store.set_active_session(
                ActiveSessionPointer(None, None, instant),
                expected_source_hash=None,
            )
        if not store.verify_projections().current:
            store.rebuild_projections()
    return CommandOutcome(
        command="runtime init",
        data={
            "task_pointer_created": write and task_missing,
            "session_pointer_created": write and session_missing,
            "would_change": would_change,
            "written": write,
        },
        messages=(
            "Coding runtime initialization plan validated; dry-run made no changes."
            if not write
            else "Coding runtime initialization ensured; projections are current."
        ,),
        changed=write and would_change,
        dry_run=not write,
    )
