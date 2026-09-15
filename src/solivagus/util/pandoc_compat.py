"""Normalize OCR Markdown so Pandoc writers (esp. LaTeX/PDF) see native AST nodes.

PaddleOCR-VL / PaddleX emit centered HTML <img> and spaced inline math ($ ... $).
Pandoc treats those as RawInline HTML / plain Str, so XeLaTeX drops figures and
runs \\circ in text mode. Canonical Solivagus Markdown uses Pandoc Image syntax
and tight $math$ delimiters instead.
"""

from __future__ import annotations

import re
from html import unescape

# <div style="text-align: center;"><img ... /></div>  (PaddleX pretty markdown)
_CENTERED_IMG_DIV_RE = re.compile(
    r"""
    <div\b[^>]*\bstyle\s*=\s*["'][^"']*text-align\s*:\s*center[^"']*["'][^>]*>
    \s*
    <img\b([^>]*)>
    \s*
    </div>
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

# Bare <img ...> (self-closing or not)
_BARE_IMG_RE = re.compile(
    r"<img\b([^>]*)>",
    re.IGNORECASE | re.DOTALL,
)

_ATTR_RE = re.compile(
    r"""(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.DOTALL,
)

# Inline $ ... $ with optional whitespace inside delimiters (not $$).
_SPACED_INLINE_MATH_RE = re.compile(
    r"(?<!\$)\$(?!\$)\s*((?:\\.|[^$\n])+?)\s*\$(?!\$)",
)


def _attr_map(attr_blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attr_blob or ""):
        out[match.group("name").lower()] = unescape(match.group("val"))
    return out


def _img_attrs_to_pandoc(attr_blob: str) -> str:
    attrs = _attr_map(attr_blob)
    src = (attrs.get("src") or "").strip()
    if not src:
        return ""
    alt = (attrs.get("alt") or "Image").strip() or "Image"
    # Escape ] and ) lightly for markdown safety
    alt = alt.replace("]", "\\]")
    width = (attrs.get("width") or "").strip()
    link = f"![{alt}]({src})"
    if width:
        # Pandoc attribute syntax: {width=81%}
        link += f"{{width={width}}}"
    return link


def html_images_to_pandoc(markdown: str) -> str:
    """Replace centered HTML img wrappers (and remaining bare imgs) with Pandoc Image."""

    def _centered(match: re.Match[str]) -> str:
        converted = _img_attrs_to_pandoc(match.group(1))
        return converted if converted else match.group(0)

    text = _CENTERED_IMG_DIV_RE.sub(_centered, markdown)

    def _bare(match: re.Match[str]) -> str:
        converted = _img_attrs_to_pandoc(match.group(1))
        return converted if converted else match.group(0)

    return _BARE_IMG_RE.sub(_bare, text)


def normalize_inline_math_delimiters(markdown: str) -> str:
    """Rewrite `$  expr  $` → `$expr$` so Pandoc recognizes InlineMath."""

    def _fix(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body:
            return match.group(0)
        return f"${body}$"

    # Protect fenced code / display $$ first via temporary placeholders.
    placeholders: dict[str, str] = {}
    counter = 0

    def _stash(pattern: re.Pattern[str], text: str) -> str:
        nonlocal counter

        def repl(m: re.Match[str]) -> str:
            nonlocal counter
            counter += 1
            token = f"@@PANDOC_PROTECT_{counter:05d}@@"
            placeholders[token] = m.group(0)
            return token

        return pattern.sub(repl, text)

    protected = markdown
    protected = _stash(re.compile(r"(?ms)^```.*?^```\s*$|^~~~.*?^~~~\s*$"), protected)
    protected = _stash(re.compile(r"\$\$.*?\$\$", re.DOTALL), protected)
    protected = _stash(re.compile(r"\\\[.*?\\\]", re.DOTALL), protected)
    protected = _SPACED_INLINE_MATH_RE.sub(_fix, protected)
    for token, original in placeholders.items():
        protected = protected.replace(token, original)
    return protected


def normalize_for_pandoc(markdown: str) -> str:
    """Canonical post-OCR Markdown normalization for Pandoc-native writers."""
    if not markdown:
        return markdown
    text = html_images_to_pandoc(markdown)
    text = normalize_inline_math_delimiters(text)
    return text
