"""Normalize OCR Markdown so Pandoc writers (esp. LaTeX/PDF) see native AST nodes.

PaddleOCR-VL / PaddleX emit centered HTML <img> and spaced inline math ($ ... $).
Pandoc treats those as RawInline HTML / plain Str, so XeLaTeX drops figures and
runs \\circ in text mode. Canonical Solivagus Markdown uses Pandoc Image syntax
and tight $math$ delimiters instead.

Code fences / inline code are protected before any rewrite. Currency-like `$…$`
pairs are left alone (conservative).
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

_BARE_IMG_RE = re.compile(
    r"<img\b([^>]*)>",
    re.IGNORECASE | re.DOTALL,
)

_ATTR_RE = re.compile(
    r"""(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.DOTALL,
)

_FENCED_CODE_RE = re.compile(r"(?ms)^```.*?^```\s*$|^~~~.*?^~~~\s*$")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_DISPLAY_DOLLAR_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_DISPLAY_BRACKET_RE = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_ESCAPED_DOLLAR_RE = re.compile(r"\\\$")

# Inline $ ... $ with optional whitespace inside delimiters (not $$).
_SPACED_INLINE_MATH_RE = re.compile(
    r"(?<!\$)\$(?!\$)\s*((?:\\.|[^$\n])+?)\s*\$(?!\$)",
)

# TeX / math signals — refuse plain multi-word / money-like bodies.
_MATH_SIGNAL_RE = re.compile(
    r"[\\^_{}=]|\\[a-zA-Z]+|[A-Za-z][_^]|[_^]\{|[+\-*/]=|[≤≥≠∈∑∫]"
)
_MONEY_OR_NUMBER_RE = re.compile(r"^[\d.,\s]+$")
_SHORT_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,7}$")


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
    alt = alt.replace("]", "\\]")
    width = (attrs.get("width") or "").strip()
    link = f"![{alt}]({src})"
    if width:
        link += f"{{width={width}}}"
    return link


def _stash_regions(
    text: str,
    patterns: list[re.Pattern[str]],
    *,
    prefix: str,
) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    counter = 0
    protected = text
    for pattern in patterns:
        def repl(m: re.Match[str], _p=pattern) -> str:
            nonlocal counter
            counter += 1
            token = f"@@{prefix}_{counter:05d}@@"
            placeholders[token] = m.group(0)
            return token

        protected = pattern.sub(repl, protected)
    return protected, placeholders


def _restore(text: str, placeholders: dict[str, str]) -> str:
    out = text
    # Restore longest tokens first in case of accidental nesting (should not happen).
    for token in sorted(placeholders, key=len, reverse=True):
        out = out.replace(token, placeholders[token])
    return out


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


def _looks_like_inline_math(body: str) -> bool:
    """Conservative: only tighten delimiter spacing when body is clearly math-like."""
    b = body.strip()
    if not b:
        return False
    if _MONEY_OR_NUMBER_RE.fullmatch(b):
        return False
    if _MATH_SIGNAL_RE.search(b):
        return True
    # "$ x $" / "$x$" style single identifiers — only when already spaced in source
    # and not multi-word English ("5 and").
    if " " in b:
        return False
    if _SHORT_IDENT_RE.fullmatch(b):
        return True
    return False


def normalize_inline_math_delimiters(markdown: str) -> str:
    """Rewrite `$  expr  $` → `$expr$` when *expr* looks like math (not currency)."""

    def _fix(match: re.Match[str]) -> str:
        body = match.group(1)
        if not _looks_like_inline_math(body):
            return match.group(0)
        return f"${body.strip()}$"

    protected, placeholders = _stash_regions(
        markdown,
        [
            _FENCED_CODE_RE,
            _INLINE_CODE_RE,
            _DISPLAY_DOLLAR_RE,
            _DISPLAY_BRACKET_RE,
            _ESCAPED_DOLLAR_RE,
        ],
        prefix="PANDOC_MATH",
    )
    protected = _SPACED_INLINE_MATH_RE.sub(_fix, protected)
    return _restore(protected, placeholders)


def normalize_for_pandoc(markdown: str) -> str:
    """Canonical post-OCR Markdown normalization for Pandoc-native writers."""
    if not markdown:
        return markdown
    # Protect code (and display math) before any HTML-img rewrite.
    protected, placeholders = _stash_regions(
        markdown,
        [_FENCED_CODE_RE, _INLINE_CODE_RE],
        prefix="PANDOC_CODE",
    )
    protected = html_images_to_pandoc(protected)
    protected = normalize_inline_math_delimiters(protected)
    return _restore(protected, placeholders)
