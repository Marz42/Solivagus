"""Split a failing translation unit into safer halves (brief §19.2)."""

from __future__ import annotations

import re

from solivagus.util.markdown import iter_markdown_blocks

_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")


def bisect_source_text(text: str) -> tuple[str, str] | None:
    """Return two non-empty halves, or None if the unit cannot be split safely.

    Preference order:
    1. Markdown block mid-point (tables/fences stay whole)
    2. Blank-line paragraphs inside a single block
    3. Sentence split for long plain text
    """
    text = (text or "").strip()
    if not text:
        return None

    blocks = [b.strip() for b in iter_markdown_blocks(text) if b.strip()]
    if len(blocks) >= 2:
        mid = max(1, len(blocks) // 2)
        left = "\n\n".join(blocks[:mid]).strip()
        right = "\n\n".join(blocks[mid:]).strip()
        if left and right:
            return left, right

    # Single atomic-ish block: try paragraphs.
    body = blocks[0] if blocks else text
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) >= 2:
        mid = max(1, len(paras) // 2)
        left = "\n\n".join(paras[:mid]).strip()
        right = "\n\n".join(paras[mid:]).strip()
        if left and right:
            return left, right

    # Sentence split only when long enough to be worth it.
    if len(body) < 800:
        return None
    parts = [p.strip() for p in _SENTENCE_RE.split(body) if p.strip()]
    if len(parts) < 2:
        return None
    mid = max(1, len(parts) // 2)
    left = " ".join(parts[:mid]).strip()
    right = " ".join(parts[mid:]).strip()
    if not left or not right:
        return None
    # Avoid tiny shards.
    if min(len(left), len(right)) < 200:
        return None
    return left, right
