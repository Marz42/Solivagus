"""Structured diagnostics shared by Paradigma application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    source: str = "<unknown>"
    line: int | None = None
    column: int | None = None
    severity: Severity = Severity.ERROR
    details: dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        location = self.source
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        return f"[{self.code}] {location}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "severity": self.severity.value,
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        if self.details:
            payload["details"] = self.details
        return payload

