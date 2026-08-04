"""References section handling."""

from __future__ import annotations

import re
from typing import Literal

ReferencesMode = Literal["keep", "translate_titles", "translate_all"]

_HEADING_RE = re.compile(
    r"(?im)^(#{1,6}\s*)(References|Bibliography|Works Cited)\b(.*)$"
)


def apply_references_mode(markdown: str, mode: ReferencesMode = "keep") -> str:
    """Apply references policy to a markdown fragment or full document.

    ``keep`` (default / production): translate only the section heading to 参考文献;
    leave bibliographic entries, DOIs, authors, and page numbers untouched.
    ``translate_titles`` / ``translate_all`` are deferred (ADR-002); currently behave like ``keep``.
    """
    if not markdown:
        return markdown
    if mode in {"keep", "translate_titles", "translate_all"}:
        return _HEADING_RE.sub(r"\1参考文献\3", markdown)
    return markdown


def is_references_heading(line: str) -> bool:
    return bool(_HEADING_RE.match((line or "").strip()))
