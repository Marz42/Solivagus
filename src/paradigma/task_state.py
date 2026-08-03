"""Strict active-task lifecycle parsing."""

from __future__ import annotations

from enum import Enum
import re

from .errors import ParadigmaError


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    ABORTED = "aborted"


class TaskStateFailure(ParadigmaError, ValueError):
    code = "PD_TASK_INVALID_STATUS"


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def parse_task_status(text: str) -> TaskStatus:
    raw = extract_section(text, "Current Status")
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(values) != 1:
        raise TaskStateFailure(
            "Current Status must contain exactly one status value"
        )
    try:
        return TaskStatus(values[0])
    except ValueError as error:
        allowed = ", ".join(status.value for status in TaskStatus)
        raise TaskStateFailure(
            f"unknown task status {values[0]!r}; expected one of: {allowed}"
        ) from error


def task_identifier(text: str) -> str:
    raw = extract_section(text, "Task ID")
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    return values[0] if values else ""
