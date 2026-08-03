"""Repository lint, link, size, design, and aggregate check services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
import re

from ..config import ParadigmaConfig, require_valid_config
from ..diagnostics import Diagnostic, Severity
from ..errors import ParseFailure
from ..parser import (
    FlatValue,
    flatten_mapping,
    parse_flat_frontmatter,
    parse_markdown_text,
    read_utf8_text,
)
from ..schema import (
    load_schema_registry,
    validate_concept,
    validate_generated_index,
)
from ..task_state import TaskStateFailure, parse_task_status
from .indexing import index_verify_outcome
from .outcomes import CommandOutcome
from .versioning import version_outcome


MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _concept_and_index_files(
    config: ParadigmaConfig,
) -> tuple[list[Path], list[Path]]:
    concepts: list[Path] = []
    indexes: list[Path] = []
    for knowledge_root in config.knowledge_roots:
        if not knowledge_root.exists():
            continue
        for path in sorted(knowledge_root.rglob("*.md")):
            if path.name in config.reserved_filenames:
                indexes.append(path)
            else:
                concepts.append(path)
    return concepts, indexes


def lint_outcome(repository_root: Path, *, strict: bool = True) -> CommandOutcome:
    root = repository_root.resolve()
    config = require_valid_config(root)
    registry = load_schema_registry(
        root / ".paradigma" / "schemas" / "paradigma-types.schema.yaml"
    )
    concepts, indexes = _concept_and_index_files(config)
    diagnostics: list[Diagnostic] = []
    for path in concepts:
        try:
            metadata, body = parse_flat_frontmatter(path)
            diagnostics.extend(
                validate_concept(
                    metadata,
                    body,
                    registry,
                    source=_relative(root, path),
                    strict=strict,
                )
            )
        except ParseFailure as error:
            diagnostics.append(error.diagnostic)
    for path in indexes:
        try:
            diagnostics.extend(
                validate_generated_index(
                    read_utf8_text(path),
                    source=_relative(root, path),
                    strict=strict,
                )
            )
        except ParseFailure as error:
            diagnostics.append(error.diagnostic)
    return CommandOutcome(
        command="lint",
        data={
            "concept_count": len(concepts),
            "index_count": len(indexes),
            "errors": sum(
                item.severity is Severity.ERROR for item in diagnostics
            ),
            "warnings": sum(
                item.severity is Severity.WARNING for item in diagnostics
            ),
            "mode": "strict" if strict else "normal",
        },
        diagnostics=tuple(diagnostics),
    )


def _strip_code_content(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    return "\n".join(
        "" if line.startswith(("    ", "\t")) else line
        for line in text.splitlines()
    )


def _markdown_targets(body: str) -> list[str]:
    targets: list[str] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(body):
        target = match.group(1).strip()
        if " " in target and not target.startswith("<"):
            target = target.split()[0]
        targets.append(target.strip("<>"))
    return targets


def _relation_targets(
    metadata: dict[str, FlatValue],
) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not key.startswith("paradigma.relations."):
            continue
        kind = key.rsplit(".", 1)[-1]
        values = value if isinstance(value, list) else [value]
        targets.extend(
            (kind, str(item).strip())
            for item in values
            if str(item).strip()
        )
    return targets


def _is_external(target: str) -> bool:
    return target.lower().startswith(("http://", "https://", "mailto:", "tel:"))


def _strip_fragment(target: str) -> str:
    return target.split("#", 1)[0].strip()


def _knowledge_root_for(path: Path, roots: tuple[Path, ...]) -> Path | None:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def _resolve_target(
    source: Path, target: str, roots: tuple[Path, ...], repository_root: Path
) -> Path | None:
    clean = unquote(_strip_fragment(target).strip())
    if not clean or _is_external(clean):
        return None
    if clean.startswith("/"):
        bundle_root = _knowledge_root_for(source, roots)
        return (
            (bundle_root / clean.lstrip("/")).resolve()
            if bundle_root is not None
            else (repository_root / clean.lstrip("/")).resolve()
        )
    return (source.parent / clean).resolve()


def _target_exists(path: Path) -> bool:
    return path.exists() or (path.suffix == "" and (path / "index.md").exists())


def link_outcome(repository_root: Path) -> CommandOutcome:
    root = repository_root.resolve()
    config = require_valid_config(root)
    files = [
        path
        for knowledge_root in config.knowledge_roots
        if knowledge_root.exists()
        for path in sorted(knowledge_root.rglob("*.md"))
    ]
    diagnostics: list[Diagnostic] = []
    for path in files:
        try:
            text = read_utf8_text(path)
            if text.splitlines()[:1] == ["---"]:
                parsed = parse_markdown_text(text, source=str(path))
                metadata = flatten_mapping(parsed.metadata)
                body = parsed.body
            else:
                metadata, body = {}, text
        except ParseFailure as error:
            diagnostics.append(error.diagnostic)
            continue
        targets = [
            ("markdown", target)
            for target in _markdown_targets(_strip_code_content(body))
        ]
        targets.extend(_relation_targets(metadata))
        for kind, target in targets:
            if _is_external(target) or not _strip_fragment(target):
                continue
            resolved = _resolve_target(path, target, config.knowledge_roots, root)
            if resolved is not None and not _target_exists(resolved):
                diagnostics.append(
                    Diagnostic(
                        "PD_LINK_TARGET_MISSING",
                        f"missing {kind} target `{target}`",
                        _relative(root, path),
                        severity=(
                            Severity.WARNING
                            if kind == "planned"
                            else Severity.ERROR
                        ),
                        details={"kind": kind, "target": target},
                    )
                )
    return CommandOutcome(
        command="links",
        data={
            "file_count": len(files),
            "errors": sum(
                item.severity is Severity.ERROR for item in diagnostics
            ),
            "warnings": sum(
                item.severity is Severity.WARNING for item in diagnostics
            ),
        },
        diagnostics=tuple(diagnostics),
    )


@dataclass(frozen=True)
class SizeStatus:
    path: Path
    lines: int
    warn_at: int
    error_at: int
    category: str

    @property
    def severity(self) -> Severity | None:
        if self.lines > self.error_at:
            return Severity.ERROR
        if self.lines > self.warn_at:
            return Severity.WARNING
        return None


def hot_size_outcome(repository_root: Path) -> CommandOutcome:
    root = repository_root.resolve()
    config = require_valid_config(root)
    active = root / config.runtime_root_name / "active-task.md"
    progress = root / config.logs_root_name / "progress" / "index.md"
    statuses: list[SizeStatus] = []
    if active.exists():
        try:
            parse_task_status(read_utf8_text(active))
        except TaskStateFailure as error:
            return CommandOutcome(
                command="hot-size",
                diagnostics=(
                    Diagnostic(error.code, str(error), _relative(root, active)),
                ),
            )
        statuses.append(
            SizeStatus(active, len(read_utf8_text(active).splitlines()), 160, 260, "runtime")
        )
    if progress.exists():
        statuses.append(
            SizeStatus(progress, len(read_utf8_text(progress).splitlines()), 160, 260, "progress")
        )
    knowledge = root / "memory-bank" / "knowledge"
    if knowledge.exists():
        for path in sorted(knowledge.rglob("*.md")):
            if path.name in config.reserved_filenames:
                continue
            try:
                metadata, _body = parse_flat_frontmatter(path)
            except ParseFailure as error:
                return CommandOutcome(command="hot-size", diagnostics=(error.diagnostic,))
            if metadata.get("paradigma.temperature") == "hot":
                statuses.append(
                    SizeStatus(path, len(read_utf8_text(path).splitlines()), 260, 420, "knowledge")
                )
    diagnostics = tuple(
        Diagnostic(
            "PD_HOT_SIZE_EXCEEDED"
            if item.severity is Severity.ERROR
            else "PD_HOT_SIZE_WARNING",
            f"{item.lines} lines; warn>{item.warn_at}, error>{item.error_at}",
            _relative(root, item.path),
            severity=item.severity or Severity.INFO,
        )
        for item in statuses
        if item.severity is not None
    )
    return CommandOutcome(
        command="hot-size",
        data={
            "items": [
                {
                    "path": _relative(root, item.path),
                    "lines": item.lines,
                    "warn_at": item.warn_at,
                    "error_at": item.error_at,
                    "category": item.category,
                }
                for item in statuses
            ]
        },
        diagnostics=diagnostics,
    )


def design_outcome(repository_root: Path) -> CommandOutcome:
    path = repository_root.resolve() / "DESIGN.md"
    if not path.exists():
        return CommandOutcome(command="design", data={"present": False})
    content = path.read_text(encoding="utf-8")
    diagnostics: list[Diagnostic] = []
    if not any(line.strip() == "---" for line in content.splitlines()[:5]):
        diagnostics.append(
            Diagnostic(
                "PD_DESIGN_FRONTMATTER_MISSING",
                "DESIGN.md has no YAML frontmatter delimiter",
                "DESIGN.md",
                severity=Severity.WARNING,
            )
        )
    for token in ("colors:", "typography:"):
        if token not in content.lower():
            diagnostics.append(
                Diagnostic(
                    "PD_DESIGN_TOKEN_SECTION_MISSING",
                    f"DESIGN.md may be missing `{token[:-1]}` tokens",
                    "DESIGN.md",
                    severity=Severity.WARNING,
                )
            )
    return CommandOutcome(
        command="design",
        data={"present": True},
        diagnostics=tuple(diagnostics),
    )


def check_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    root = repository_root.resolve()
    steps = (
        version_outcome(root, dry_run=dry_run),
        lint_outcome(root),
        link_outcome(root),
        index_verify_outcome(root, dry_run=dry_run),
        hot_size_outcome(root),
        design_outcome(root),
    )
    diagnostics = tuple(
        diagnostic for step in steps for diagnostic in step.diagnostics
    )
    return CommandOutcome(
        command="check",
        data={
            "passed": sum(step.ok for step in steps),
            "total": len(steps),
            "steps": [
                {
                    "name": step.command,
                    "ok": step.ok,
                    "data": step.data,
                    "diagnostics": [item.to_dict() for item in step.diagnostics],
                }
                for step in steps
            ],
        },
        messages=(
            f"All {len(steps)} checks passed."
            if all(step.ok for step in steps)
            else f"{sum(not step.ok for step in steps)}/{len(steps)} checks failed.",
        ),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )
