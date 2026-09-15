"""Markdown protect / passthrough / split helpers ported from the MVP hotfix."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

PASSTHROUGH_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = [
    (
        "html_table_wrapper",
        re.compile(
            r"<div\b[^>]*>\s*<table\b[^>]*>.*?</table>\s*</div>",
            re.DOTALL | re.IGNORECASE,
        ),
    ),
    (
        "html_table",
        re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE),
    ),
    (
        "html_comment",
        re.compile(r"<!--.*?-->", re.DOTALL),
    ),
    (
        "source_anchor",
        re.compile(
            r"<a\b[^>]*\bid=[\"']source-page-\d+[\"'][^>]*>\s*</a>",
            re.DOTALL | re.IGNORECASE,
        ),
    ),
]

PROTECT_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"(?ms)^```.*?^```\s*$|^~~~.*?^~~~\s*$"),
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"!\[[^\]]*\]\([^\n)]*\)(?:\{[^}\n]*\})?"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"(?<!\$)\$(?!\$)(?:\\.|[^$\n])+?\$(?!\$)"),
    re.compile(r"https?://[^\s<>\])]+"),
    re.compile(r"<[^>\n]+>"),
]


class ProtectError(ValueError):
    pass


def iter_markdown_blocks(markdown: str) -> Iterable[str]:
    lines = markdown.splitlines()
    current: list[str] = []
    in_fence = False
    fence_marker = ""
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not in_fence and (
            stripped.startswith("```") or stripped.startswith("~~~")
        ):
            if current and not in_table:
                yield "\n".join(current).rstrip()
                current = []
            in_fence = True
            fence_marker = stripped[:3]
            current.append(line)
            continue
        if in_fence:
            current.append(line)
            if stripped.startswith(fence_marker):
                yield "\n".join(current).rstrip()
                current = []
                in_fence = False
                fence_marker = ""
            continue

        if stripped.lower().startswith("<table") or (
            stripped.lower().startswith("<div") and "<table" in stripped.lower()
        ):
            if current and not in_table:
                yield "\n".join(current).rstrip()
                current = []
            in_table = True
            current.append(line)
            if "</table>" in stripped.lower():
                yield "\n".join(current).rstrip()
                current = []
                in_table = False
            continue
        if in_table:
            current.append(line)
            if "</table>" in stripped.lower():
                yield "\n".join(current).rstrip()
                current = []
                in_table = False
            continue

        if stripped == "":
            if current:
                yield "\n".join(current).rstrip()
                current = []
            continue
        current.append(line)

    if current:
        yield "\n".join(current).rstrip()


def split_markdown(markdown: str, chunk_chars: int) -> list[str]:
    if chunk_chars < 2000:
        raise ValueError("--chunk-chars 不应低于 2000。")

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for block in iter_markdown_blocks(markdown):
        block_len = len(block) + 2
        if current and current_len + block_len > chunk_chars:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len

    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def split_passthrough_segments(text: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    cursor = 0
    while cursor < len(text):
        earliest_kind: str | None = None
        earliest_match: re.Match[str] | None = None
        for kind, pattern in PASSTHROUGH_PATTERNS:
            match = pattern.search(text, cursor)
            if match is None:
                continue
            if earliest_match is None or match.start() < earliest_match.start():
                earliest_kind = kind
                earliest_match = match
            elif (
                earliest_match is not None
                and match.start() == earliest_match.start()
                and match.end() > earliest_match.end()
            ):
                earliest_kind = kind
                earliest_match = match
        if earliest_match is None or earliest_kind is None:
            if cursor < len(text):
                segments.append(("text", text[cursor:]))
            break
        if earliest_match.start() > cursor:
            segments.append(("text", text[cursor : earliest_match.start()]))
        segments.append((earliest_kind, earliest_match.group(0)))
        cursor = earliest_match.end()
    return [(kind, value) for kind, value in segments if value]


def protect_markdown(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    counter = 1

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = f"@@PRESERVE_{counter:05d}@@"
        counter += 1
        placeholders[token] = match.group(0)
        return token

    protected = text
    for pattern in PROTECT_PATTERNS:
        protected = pattern.sub(replace, protected)
    return protected, placeholders


def restore_markdown(text: str, placeholders: dict[str, str]) -> str:
    missing = [token for token in placeholders if text.count(token) != 1]
    if missing:
        preview = ", ".join(missing[:8])
        raise ProtectError(
            f"译文占位符缺失、重复或被改写：{preview}"
            + (" ..." if len(missing) > 8 else "")
        )
    restored = text
    for token, original in placeholders.items():
        restored = restored.replace(token, original)
    return restored


def make_untranslated_fallback(block_id: str, source_chunk: str, error: Exception) -> str:
    safe_error = str(error).replace("\n", " ").strip()
    return (
        f"<!-- translation-block: {block_id} -->\n\n"
        f"> [翻译警告] 本块自动翻译失败，已保留英文原文以便无人值守任务继续。  \n"
        f"> 错误：`{safe_error[:500]}`\n\n"
        f"{source_chunk.strip()}\n"
    )
