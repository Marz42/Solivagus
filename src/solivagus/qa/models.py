"""QA finding models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QAFinding:
    code: str
    message: str
    severity: Severity = Severity.MEDIUM
    detail: str | None = None
    repaired: bool = False


@dataclass
class UnitQAResult:
    unit_key: str
    status: str  # pass | warn | fail | fallback | repaired
    findings: list[QAFinding] = field(default_factory=list)
    source_text: str = ""
    translation_text: str = ""
    html_tables_kept: int = 0

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def passed(self) -> bool:
        return self.status in {"pass", "repaired"} and self.high_count == 0


@dataclass
class QAReportSummary:
    unit_count: int = 0
    passed: int = 0
    repaired: int = 0
    fallback: int = 0
    warned: int = 0
    failed: int = 0
    html_tables_kept: int = 0
    units: list[UnitQAResult] = field(default_factory=list)
