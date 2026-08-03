"""Derived workspace versus upstream diagnosis service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib

from ..diagnostics import Diagnostic, Severity
from ..parser import FlatValue, load_flat_yaml_file
from .outcomes import CommandOutcome


@dataclass(frozen=True)
class Gap:
    category: str
    severity: str
    kind: str
    item: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "severity": self.severity,
            "kind": self.kind,
            "item": self.item,
            "detail": self.detail,
        }


def _top_level(path: Path) -> dict[str, FlatValue]:
    return load_flat_yaml_file(path, missing_ok=True)


def detect_version(project: Path) -> str:
    config = _top_level(project / ".paradigma" / "config.yaml")
    version = config.get("installed_distribution_version") or config.get(
        "paradigma_harness_version"
    )
    if isinstance(version, str) and version:
        return version
    if (project / "memory_bank").is_dir():
        return "pre-0.2.0 (legacy flat memory_bank/)"
    memory_bank = project / "memory-bank"
    if memory_bank.is_dir():
        if (memory_bank / "runtime").is_dir():
            return "0.3.0+ (OKF three-state, exact version unknown)"
        return "0.2.x (flat memory-bank/)"
    return "unknown"


def upstream_version(upstream: Path) -> str:
    version_path = upstream / "VERSION"
    if version_path.exists():
        version = version_path.read_text(encoding="utf-8-sig").strip()
        if version:
            return version
    config = _top_level(upstream / ".paradigma" / "config.yaml")
    value = config.get("installed_distribution_version") or config.get(
        "paradigma_harness_version"
    )
    return str(value) if value else "unknown"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _files(path: Path, pattern: str) -> set[str]:
    return {item.name for item in path.glob(pattern)} if path.is_dir() else set()


def _compare_file_sets(
    project: Path,
    upstream: Path,
    relative: str,
    pattern: str,
    category: str,
) -> list[Gap]:
    upstream_root = upstream / relative
    project_root = project / relative
    expected = _files(upstream_root, pattern)
    actual = _files(project_root, pattern)
    if not expected:
        return []
    if not actual:
        return [
            Gap(
                category,
                "error",
                "missing",
                f"{category} completely missing",
                ", ".join(sorted(expected)),
            )
        ]
    gaps: list[Gap] = []
    missing = expected - actual
    if missing:
        gaps.append(
            Gap(
                category,
                "warning",
                "missing",
                f"missing {len(missing)} {category} file(s)",
                ", ".join(sorted(missing)),
            )
        )
    for name in sorted(expected & actual):
        if _hash(upstream_root / name) != _hash(project_root / name):
            gaps.append(
                Gap(
                    category,
                    "warning",
                    "outdated",
                    f"content differs: {name}",
                    "review against upstream",
                )
            )
    extra = actual - expected
    if category == "tools" and extra:
        gaps.append(
            Gap(
                category,
                "info",
                "extra",
                f"project-owned tools: {', '.join(sorted(extra))}",
            )
        )
    return gaps


def diagnose(project: Path, upstream: Path) -> tuple[str, str, list[Gap]]:
    project = project.resolve()
    upstream = upstream.resolve()
    detected = detect_version(project)
    latest = upstream_version(upstream)
    gaps: list[Gap] = []
    if detected == "unknown":
        gaps.append(
            Gap(
                "structure",
                "error",
                "missing",
                "Paradigma harness not detected",
                "project has no memory-bank/ or memory_bank/ directory",
            )
        )
        return detected, latest, gaps
    if detected != latest:
        gaps.append(
            Gap(
                "config",
                "error",
                "mismatch",
                f"version mismatch: {detected} vs {latest}",
            )
        )
    for relative in (
        "memory-bank/runtime",
        "memory-bank/logs",
        "memory-bank/knowledge",
        "memory-bank-template",
        ".paradigma/schemas",
    ):
        if not (project / relative).is_dir():
            gaps.append(
                Gap("structure", "error", "missing", f"missing directory: {relative}")
            )
    if (
        (project / "memory-bank" / "logs").is_dir()
        and not (project / "memory-bank" / "logs" / "progress").is_dir()
    ):
        gaps.append(
            Gap(
                "structure",
                "warning",
                "missing",
                "missing directory: memory-bank/logs/progress",
            )
        )
    gaps.extend(
        _compare_file_sets(
            project, upstream, ".paradigma/tools", "*.py", "tools"
        )
    )
    gaps.extend(
        _compare_file_sets(
            project, upstream, ".paradigma/schemas", "*.yaml", "schema"
        )
    )
    upstream_config = upstream / ".paradigma" / "config.yaml"
    project_config = project / ".paradigma" / "config.yaml"
    if upstream_config.exists() and not project_config.exists():
        gaps.append(
            Gap("config", "error", "missing", ".paradigma/config.yaml missing")
        )
    elif upstream_config.exists():
        expected = _top_level(upstream_config)
        actual = _top_level(project_config)
        missing = set(expected) - set(actual)
        if missing:
            gaps.append(
                Gap(
                    "config",
                    "warning",
                    "missing",
                    f"missing {len(missing)} config field(s)",
                    ", ".join(sorted(missing)),
                )
            )
        if "paradigma_harness_version" in actual:
            gaps.append(
                Gap(
                    "config",
                    "warning",
                    "deprecated",
                    "legacy paradigma_harness_version is present",
                )
            )
    for relative in (
        "AGENT_RULES.md",
        "INIT_PROMPT.md",
        ".cursor/rules/memory-bank-protocol.mdc",
    ):
        expected = upstream / relative
        actual = project / relative
        if not expected.exists():
            continue
        if not actual.exists():
            gaps.append(
                Gap("protocol", "error", "missing", f"missing protocol: {relative}")
            )
        elif _hash(expected) != _hash(actual):
            gaps.append(
                Gap(
                    "protocol",
                    "info",
                    "mismatch",
                    f"protocol differs: {relative}",
                    "manual review required",
                )
            )
    return detected, latest, gaps


def diagnose_outcome(
    project: Path, upstream: Path, *, dry_run: bool = False
) -> CommandOutcome:
    detected, latest, gaps = diagnose(project, upstream)
    severity_map = {
        "error": Severity.ERROR,
        "warning": Severity.WARNING,
        "info": Severity.INFO,
    }
    diagnostics = tuple(
        Diagnostic(
            "PD_DIAGNOSE_GAP",
            gap.item,
            gap.category,
            severity=severity_map[gap.severity],
            details=gap.to_dict(),
        )
        for gap in gaps
    )
    errors = sum(gap.severity == "error" for gap in gaps)
    warnings = sum(gap.severity == "warning" for gap in gaps)
    infos = sum(gap.severity == "info" for gap in gaps)
    return CommandOutcome(
        command="diagnose",
        data={
            "project_path": str(project.resolve()),
            "upstream_path": str(upstream.resolve()),
            "detected_version": detected,
            "upstream_version": latest,
            "version_match": detected == latest,
            "gaps": [gap.to_dict() for gap in gaps],
            "summary": {
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
                "total": len(gaps),
            },
        },
        messages=(
            "No harness gaps detected."
            if not gaps
            else f"Detected {len(gaps)} harness gap(s).",
        ),
        diagnostics=diagnostics,
        dry_run=dry_run,
        exit_code_override=(
            2 if detected == "unknown" else 1 if errors or warnings else 0
        ),
    )
