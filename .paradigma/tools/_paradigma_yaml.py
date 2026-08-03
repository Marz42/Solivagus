"""Deprecated import shim for the package YAML/frontmatter parser."""

from _bootstrap import ensure_package

ensure_package()

from paradigma.errors import ParseFailure
from paradigma.parser import (
    FlatValue,
    ParseDiagnostic,
    ParsedMarkdown,
    flatten_mapping,
    load_flat_yaml_file,
    load_yaml_file,
    load_yaml_text,
    parse_flat_frontmatter,
    parse_markdown_file,
    parse_markdown_text,
    read_utf8_text,
)

__all__ = [
    "FlatValue",
    "ParseDiagnostic",
    "ParseFailure",
    "ParsedMarkdown",
    "flatten_mapping",
    "load_flat_yaml_file",
    "load_yaml_file",
    "load_yaml_text",
    "parse_flat_frontmatter",
    "parse_markdown_file",
    "parse_markdown_text",
    "read_utf8_text",
]
