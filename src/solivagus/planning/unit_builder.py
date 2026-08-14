"""Pack structural nodes into translation units (token budgets)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from solivagus.structure.models import NodeType, StructuralNode
from solivagus.util.text import sha256_text

_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass
class PlannedUnit:
    unit_key: str
    sequence_index: int
    source_text: str
    source_hash: str
    source_tokens: int
    estimated_output_tokens: int
    heading_path: str
    status: str = "pending"


@dataclass
class UnitBudget:
    target_tokens: int = 12_000
    max_tokens: int = 24_000
    min_tokens: int = 1_500


def _join_nodes(nodes: list[StructuralNode]) -> str:
    return "\n\n".join(n.source_text.rstrip() for n in nodes if n.source_text.strip()) + "\n"


def _split_paragraph_sentences(text: str, max_tokens: int, count_fn) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_RE.split(text.strip()) if p.strip()]
    if len(parts) <= 1:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for part in parts:
        tokens = count_fn(part)
        if current and current_tokens + tokens > max_tokens:
            chunks.append(" ".join(current))
            current = [part]
            current_tokens = tokens
        else:
            current.append(part)
            current_tokens += tokens
    if current:
        chunks.append(" ".join(current))
    return chunks


def build_translation_units(
    nodes: list[StructuralNode],
    *,
    budget: UnitBudget | None = None,
    count_fn=None,
    estimate_output_fn=None,
) -> list[PlannedUnit]:
    """Pack nodes into units without splitting atomic protected nodes."""
    budget = budget or UnitBudget()
    if count_fn is None:
        from solivagus.planning.tokenizer import approximate_token_count

        count_fn = approximate_token_count
    if estimate_output_fn is None:
        estimate_output_fn = lambda tokens: int(tokens * 1.3) + 512

    units: list[PlannedUnit] = []
    current: list[StructuralNode] = []
    current_tokens = 0
    current_path = ""

    def flush() -> None:
        nonlocal current, current_tokens, current_path
        if not current:
            return
        text = _join_nodes(current)
        tokens = count_fn(text)
        index = len(units) + 1
        units.append(
            PlannedUnit(
                unit_key=f"u{index:05d}",
                sequence_index=index,
                source_text=text,
                source_hash=sha256_text(text),
                source_tokens=tokens,
                estimated_output_tokens=int(estimate_output_fn(tokens)),
                heading_path=current_path,
            )
        )
        current = []
        current_tokens = 0
        current_path = ""

    def append_text_as_nodes(text: str, template: StructuralNode) -> None:
        nonlocal current, current_tokens, current_path
        piece = StructuralNode(
            node_type=template.node_type,
            sequence_index=template.sequence_index,
            source_text=text if text.endswith("\n") else text + "\n",
            source_hash=sha256_text(text),
            token_count=count_fn(text),
            heading_level=template.heading_level,
            heading_path=template.heading_path,
            parent_temp_id=template.parent_temp_id,
            temp_id=template.temp_id,
            source_pages=template.source_pages,
            metadata=dict(template.metadata),
        )
        piece_tokens = piece.token_count
        if current and current_tokens + piece_tokens > budget.max_tokens:
            flush()
        if not current:
            current_path = piece.heading_path
        current.append(piece)
        current_tokens += piece_tokens
        if current_tokens >= budget.target_tokens:
            flush()

    for node in nodes:
        node_tokens = node.token_count or count_fn(node.source_text)
        node.token_count = node_tokens

        # Soft boundary: h1/h2 headings close the previous unit when it is large enough.
        if (
            node.node_type == NodeType.HEADING
            and node.heading_level is not None
            and node.heading_level <= 2
            and current
            and current_tokens >= budget.min_tokens
        ):
            flush()

        if node.is_atomic or node_tokens <= budget.max_tokens:
            if current and current_tokens + node_tokens > budget.max_tokens:
                flush()
            if not current:
                current_path = node.heading_path
            current.append(node)
            current_tokens += node_tokens
            if current_tokens >= budget.target_tokens and not node.is_atomic:
                # Prefer flushing after filling target, but keep atomic attachments
                # only when the next node is not required — flush when over target.
                flush()
            continue

        # Oversized non-atomic paragraph: sentence-safe split.
        flush()
        for piece in _split_paragraph_sentences(node.source_text, budget.max_tokens, count_fn):
            append_text_as_nodes(piece, node)
        flush()

    flush()
    return units
