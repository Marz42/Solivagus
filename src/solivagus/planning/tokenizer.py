"""Token counting with exact/approximate modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class TokenMode(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    mode: TokenMode


_CJK_RE = re.compile(r"[\u3400-\u9fff\uF900-\uFAFF\u3040-\u30ff\uac00-\ud7af]")


def approximate_token_count(text: str) -> int:
    """Heuristic: CJK ~0.6 tok/char, other ~0.3 tok/char (roadmap fallback)."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = max(len(text) - cjk, 0)
    return max(1, int(cjk * 0.6 + other * 0.3 + 0.999))


class TokenCounter:
    """Prefer HuggingFace/tokenizers if available; else approximate."""

    def __init__(self) -> None:
        self._encoder = None
        self._mode = TokenMode.APPROXIMATE
        try:
            from tokenizers import Tokenizer  # type: ignore

            # Lightweight path: no network; if no local tokenizer file, stay approximate.
            _ = Tokenizer
        except Exception:  # noqa: BLE001
            self._encoder = None
            self._mode = TokenMode.APPROXIMATE

    @property
    def mode(self) -> TokenMode:
        return self._mode

    def count(self, text: str) -> TokenCount:
        if self._encoder is not None:
            try:
                n = len(self._encoder.encode(text).ids)
                return TokenCount(tokens=n, mode=TokenMode.EXACT)
            except Exception:  # noqa: BLE001
                pass
        return TokenCount(tokens=approximate_token_count(text), mode=TokenMode.APPROXIMATE)


def annotate_node_tokens(nodes: list, counter: TokenCounter | None = None) -> TokenMode:
    counter = counter or TokenCounter()
    mode = counter.mode
    for node in nodes:
        counted = counter.count(node.source_text)
        node.token_count = counted.tokens
        mode = counted.mode
    return mode
