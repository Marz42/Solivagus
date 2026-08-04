"""OCR ignore-label policy (brief §9.5).

Default: keep footnote and aside_text; drop only page chrome.
Drop switches are independent so footnote and aside can be toggled separately.
"""

from __future__ import annotations

# Always ignored (page chrome).
BASE_IGNORE_LABELS: tuple[str, ...] = (
    "number",
    "header",
    "header_image",
    "footer",
    "footer_image",
)


def build_ignore_labels(
    *,
    drop_footnotes: bool = False,
    drop_aside_text: bool = False,
) -> tuple[str, ...]:
    labels = list(BASE_IGNORE_LABELS)
    if drop_footnotes:
        labels.append("footnote")
    if drop_aside_text:
        labels.append("aside_text")
    return tuple(labels)
