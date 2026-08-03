"""Safe YAML and Markdown frontmatter parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from .diagnostics import Diagnostic
from .errors import ParseFailure


FlatValue = str | list[str]
ParseDiagnostic = Diagnostic


@dataclass(frozen=True)
class ParsedMarkdown:
    metadata: dict[str, Any]
    body: str


@dataclass(frozen=True)
class Utf8Source:
    text: str
    raw: bytes


class _ParadigmaSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _ParadigmaSafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_ParadigmaSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)
_ParadigmaSafeLoader.add_constructor(
    "tag:yaml.org,2002:timestamp",
    lambda loader, node: loader.construct_scalar(node),
)


def _diagnostic_from_yaml_error(
    error: yaml.YAMLError, source: str, line_offset: int
) -> Diagnostic:
    mark = getattr(error, "problem_mark", None)
    problem = getattr(error, "problem", None) or str(error).splitlines()[0]
    code = "YAML_DUPLICATE_KEY" if "duplicate key" in problem else "YAML_SYNTAX_ERROR"
    return Diagnostic(
        code=code,
        message=problem,
        source=source,
        line=(mark.line + 1 + line_offset) if mark is not None else None,
        column=(mark.column + 1) if mark is not None else None,
    )


def load_yaml_text(
    text: str, *, source: str = "<string>", line_offset: int = 0
) -> dict[str, Any]:
    try:
        loaded = yaml.load(text, Loader=_ParadigmaSafeLoader)
    except yaml.YAMLError as error:
        raise ParseFailure(
            _diagnostic_from_yaml_error(error, source, line_offset)
        ) from error
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ParseFailure(
            Diagnostic(
                "YAML_ROOT_TYPE_ERROR",
                "YAML root must be a mapping",
                source,
                line_offset + 1,
                1,
            )
        )
    return loaded


def read_utf8_source(path: Path) -> Utf8Source:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ParseFailure(
            Diagnostic("FILE_READ_ERROR", str(error), str(path))
        ) from error
    try:
        return Utf8Source(text=raw.decode("utf-8-sig"), raw=raw)
    except UnicodeDecodeError as error:
        raise ParseFailure(
            Diagnostic(
                "ENCODING_ERROR",
                f"file is not valid UTF-8 (byte offset {error.start})",
                str(path),
            )
        ) from error


def read_utf8_text(path: Path) -> str:
    return read_utf8_source(path).text


def load_yaml_file(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if missing_ok and not path.exists():
        return {}
    return load_yaml_text(read_utf8_text(path), source=str(path))


def parse_markdown_text(text: str, *, source: str = "<string>") -> ParsedMarkdown:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ParseFailure(
            Diagnostic(
                "FRONTMATTER_MISSING",
                "document must start with YAML frontmatter",
                source,
                1,
                1,
            )
        )
    close_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if close_index is None:
        raise ParseFailure(
            Diagnostic(
                "FRONTMATTER_UNCLOSED",
                "YAML frontmatter is not closed",
                source,
                1,
                1,
            )
        )
    metadata = load_yaml_text(
        "\n".join(lines[1:close_index]), source=source, line_offset=1
    )
    return ParsedMarkdown(metadata, "\n".join(lines[close_index + 1 :]))


def parse_markdown_file(path: Path) -> ParsedMarkdown:
    return parse_markdown_text(read_utf8_text(path), source=str(path))


def _scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def flatten_mapping(data: dict[str, Any]) -> dict[str, FlatValue]:
    flattened: dict[str, FlatValue] = {}

    def visit(value: Any, prefix: str) -> None:
        if isinstance(value, dict):
            if not value and prefix:
                flattened[prefix] = []
            for key, child in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                visit(child, child_prefix)
        elif isinstance(value, list):
            flattened[prefix] = [_scalar_text(item) for item in value]
        else:
            flattened[prefix] = _scalar_text(value)

    visit(data, "")
    return flattened


def load_flat_yaml_file(
    path: Path, *, missing_ok: bool = False
) -> dict[str, FlatValue]:
    return flatten_mapping(load_yaml_file(path, missing_ok=missing_ok))


def parse_flat_frontmatter(path: Path) -> tuple[dict[str, FlatValue], str]:
    parsed = parse_markdown_file(path)
    return flatten_mapping(parsed.metadata), parsed.body
