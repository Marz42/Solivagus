"""Structural node models for Solivagus Phase 3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    BLOCKQUOTE = "blockquote"
    FORMULA = "formula"
    CODE = "code"
    IMAGE = "image"
    HTML_TABLE = "html_table"
    MARKDOWN_TABLE = "markdown_table"
    PAGE_MARKER = "page_marker"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


# Nodes that must stay atomic (never split across translation units).
ATOMIC_NODE_TYPES = frozenset(
    {
        NodeType.FORMULA,
        NodeType.CODE,
        NodeType.IMAGE,
        NodeType.HTML_TABLE,
        NodeType.MARKDOWN_TABLE,
        NodeType.PAGE_MARKER,
    }
)

# Nodes that should not be sent alone to the translation API.
NON_TRANSLATABLE = frozenset(
    {
        NodeType.FORMULA,
        NodeType.CODE,
        NodeType.IMAGE,
        NodeType.HTML_TABLE,
        NodeType.MARKDOWN_TABLE,
        NodeType.PAGE_MARKER,
    }
)


@dataclass
class StructuralNode:
    node_type: NodeType
    sequence_index: int
    source_text: str
    source_hash: str
    token_count: int = 0
    heading_level: int | None = None
    heading_path: str = ""
    parent_temp_id: int | None = None
    temp_id: int = 0
    source_pages: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_atomic(self) -> bool:
        return self.node_type in ATOMIC_NODE_TYPES

    @property
    def is_translatable(self) -> bool:
        return self.node_type not in NON_TRANSLATABLE
