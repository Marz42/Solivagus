"""Deprecated import shim for strict package task-state helpers."""

from _bootstrap import ensure_package

ensure_package()

from paradigma.task_state import (
    TaskStateFailure,
    TaskStatus,
    extract_section,
    parse_task_status,
    task_identifier,
)

__all__ = [
    "TaskStateFailure",
    "TaskStatus",
    "extract_section",
    "parse_task_status",
    "task_identifier",
]
