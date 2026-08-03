"""Value-returning application result model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .diagnostics import Diagnostic, Severity


T = TypeVar("T")


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    value: T | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(
            diagnostic.severity is Severity.ERROR
            for diagnostic in self.diagnostics
        )

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

