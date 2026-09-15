"""Parse OCR Markdown into an ordered structural node tree."""

from __future__ import annotations

import re
from typing import Iterable

from solivagus.structure.models import NodeType, StructuralNode
from solivagus.util.markdown import iter_markdown_blocks
from solivagus.util.text import sha256_text

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PAGE_COMMENT_RE = re.compile(r"<!--\s*source-page:\s*(\d+)\s*-->", re.IGNORECASE)
_PAGE_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bid=["\']source-page-(\d+)["\'][^>]*>\s*</a>',
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^(```|~~~)")
_DISPLAY_DOLLAR_RE = re.compile(r"^\$\$[\s\S]*\$\$$")
_DISPLAY_BRACKET_RE = re.compile(r"^\\\[[\s\S]*\\\]$")
_IMAGE_ONLY_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)(?:\{[^}]*\})?\s*$")
_LIST_LINE_RE = re.compile(r"^(\s*([-*+]|\d+[.)])\s+)")
_BLOCKQUOTE_RE = re.compile(r"^>")
_MD_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")


def _iter_structure_blocks(markdown: str) -> Iterable[str]:
    """Like iter_markdown_blocks, but also keep display-math `\\[...\\]` atomic."""
    for block in iter_markdown_blocks(markdown):
        # Split out leading/trailing display-math that got merged with prose.
        text = block.strip()
        if not text:
            continue
        if _DISPLAY_BRACKET_RE.match(text) or _DISPLAY_DOLLAR_RE.match(text):
            yield text
            continue
        # If block contains an embedded \\[...\\] surrounded by prose, keep as one
        # paragraph for packing; unit builder will not split atomic children.
        yield text


def _classify_block(block: str) -> tuple[NodeType, int | None, dict]:
    stripped = block.strip()
    if not stripped:
        return NodeType.UNKNOWN, None, {}

    page_comment = _PAGE_COMMENT_RE.fullmatch(stripped)
    if page_comment:
        return NodeType.PAGE_MARKER, None, {"page": int(page_comment.group(1))}
    page_anchor = _PAGE_ANCHOR_RE.fullmatch(stripped)
    if page_anchor:
        return NodeType.PAGE_MARKER, None, {"page": int(page_anchor.group(1))}

    heading = _HEADING_RE.match(stripped)
    if heading and "\n" not in stripped:
        level = len(heading.group(1))
        return NodeType.HEADING, level, {"title": heading.group(2).strip()}

    if _FENCE_RE.match(stripped):
        return NodeType.CODE, None, {}
    if _DISPLAY_DOLLAR_RE.match(stripped) or _DISPLAY_BRACKET_RE.match(stripped):
        return NodeType.FORMULA, None, {}
    if stripped.lower().startswith("<table") or (
        stripped.lower().startswith("<div") and "<table" in stripped.lower()
    ):
        return NodeType.HTML_TABLE, None, {}
    if _IMAGE_ONLY_RE.match(stripped):
        return NodeType.IMAGE, None, {}

    lines = stripped.splitlines()
    if len(lines) >= 2 and all(_MD_TABLE_LINE_RE.match(line) for line in lines[:2]):
        return NodeType.MARKDOWN_TABLE, None, {}
    if all(_LIST_LINE_RE.match(line) or line.strip() == "" for line in lines if line.strip()):
        if any(_LIST_LINE_RE.match(line) for line in lines):
            return NodeType.LIST, None, {}
    if all(_BLOCKQUOTE_RE.match(line.strip()) or line.strip() == "" for line in lines if line.strip()):
        if any(_BLOCKQUOTE_RE.match(line.strip()) for line in lines if line.strip()):
            return NodeType.BLOCKQUOTE, None, {}

    lower_title = stripped.lstrip("#").strip().lower()
    if lower_title in {"references", "bibliography", "参考资料", "参考文献"}:
        return NodeType.REFERENCE, None, {}

    return NodeType.PARAGRAPH, None, {}


def parse_markdown_structure(markdown: str) -> list[StructuralNode]:
    """Parse Markdown into ordered structural nodes with heading paths."""
    nodes: list[StructuralNode] = []
    heading_stack: list[tuple[int, str, int]] = []  # level, title, temp_id
    temp_id = 0

    for block in _iter_structure_blocks(markdown):
        node_type, heading_level, metadata = _classify_block(block)
        temp_id += 1

        parent_temp_id: int | None = None
        heading_path = ""

        if node_type == NodeType.HEADING and heading_level is not None:
            title = str(metadata.get("title") or block)
            while heading_stack and heading_stack[-1][0] >= heading_level:
                heading_stack.pop()
            parent_temp_id = heading_stack[-1][2] if heading_stack else None
            path_titles = [item[1] for item in heading_stack] + [title]
            heading_path = " / ".join(path_titles)
            heading_stack.append((heading_level, title, temp_id))
        else:
            if heading_stack:
                parent_temp_id = heading_stack[-1][2]
                heading_path = " / ".join(item[1] for item in heading_stack)

        page = metadata.get("page")
        nodes.append(
            StructuralNode(
                node_type=node_type,
                sequence_index=len(nodes) + 1,
                source_text=block if block.endswith("\n") else block + "\n",
                source_hash=sha256_text(block),
                heading_level=heading_level,
                heading_path=heading_path,
                parent_temp_id=parent_temp_id,
                temp_id=temp_id,
                source_pages=str(page) if page is not None else None,
                metadata=metadata,
            )
        )
    return nodes
