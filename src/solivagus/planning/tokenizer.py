"""Token counting: DeepSeek tokenizer → HF/tokenizers → approximate."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


class TokenMode(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    mode: TokenMode
    backend: str = "approximate"


_CJK_RE = re.compile(r"[\u3400-\u9fff\uF900-\uFAFF\u3040-\u30ff\uac00-\ud7af]")


def approximate_token_count(text: str) -> int:
    """Heuristic: CJK ~0.6 tok/char, other ~0.3 tok/char (brief fallback)."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = max(len(text) - cjk, 0)
    return max(1, int(cjk * 0.6 + other * 0.3 + 0.999))


def _try_deepseek_tokenizer() -> tuple[Callable[[str], int], str] | None:
    try:
        from deepseek_tokenizer import ds_token  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    def _count(text: str) -> int:
        encoded = ds_token.encode(text)
        if isinstance(encoded, list):
            return len(encoded)
        return len(list(encoded))

    return _count, "deepseek_tokenizer"


def _try_local_tokenizer_file(path: Path) -> tuple[Callable[[str], int], str] | None:
    if not path.is_file():
        return None
    try:
        from tokenizers import Tokenizer  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        tok = Tokenizer.from_file(str(path))
    except Exception:  # noqa: BLE001
        return None

    def _count(text: str) -> int:
        return len(tok.encode(text).ids)

    return _count, f"tokenizers:{path.name}"


def _try_transformers(model_id: str) -> tuple[Callable[[str], int], str] | None:
    try:
        from transformers import AutoTokenizer  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    except Exception:  # noqa: BLE001
        return None

    def _count(text: str) -> int:
        return len(tok.encode(text, add_special_tokens=False))

    return _count, f"transformers:{model_id}"


@lru_cache(maxsize=1)
def _resolve_encoder() -> tuple[Callable[[str], int] | None, str, TokenMode]:
    # 1) Explicit local tokenizer.json
    explicit = os.environ.get("SOLIVAGUS_TOKENIZER_FILE")
    if explicit:
        loaded = _try_local_tokenizer_file(Path(explicit))
        if loaded:
            return loaded[0], loaded[1], TokenMode.EXACT

    # 2) Lightweight deepseek_tokenizer package (V4 vocab, no network)
    loaded = _try_deepseek_tokenizer()
    if loaded:
        return loaded[0], loaded[1], TokenMode.EXACT

    # 3) Optional transformers model id (may download; opt-in via env)
    model_id = os.environ.get("SOLIVAGUS_TOKENIZER_MODEL")
    if model_id:
        loaded = _try_transformers(model_id)
        if loaded:
            return loaded[0], loaded[1], TokenMode.EXACT

    return None, "approximate", TokenMode.APPROXIMATE


class TokenCounter:
    """Prefer DeepSeek / local tokenizer; else approximate (brief §11)."""

    def __init__(self, *, force_approximate: bool = False) -> None:
        if force_approximate:
            self._encoder = None
            self._backend = "approximate"
            self._mode = TokenMode.APPROXIMATE
        else:
            encoder, backend, mode = _resolve_encoder()
            self._encoder = encoder
            self._backend = backend
            self._mode = mode

    @property
    def mode(self) -> TokenMode:
        return self._mode

    @property
    def backend(self) -> str:
        return self._backend

    def count(self, text: str) -> TokenCount:
        if self._encoder is not None:
            try:
                n = int(self._encoder(text or ""))
                return TokenCount(tokens=max(0, n), mode=TokenMode.EXACT, backend=self._backend)
            except Exception:  # noqa: BLE001
                pass
        return TokenCount(
            tokens=approximate_token_count(text),
            mode=TokenMode.APPROXIMATE,
            backend="approximate",
        )


def annotate_node_tokens(nodes: list[Any], counter: TokenCounter | None = None) -> TokenMode:
    counter = counter or TokenCounter()
    mode = counter.mode
    for node in nodes:
        counted = counter.count(node.source_text)
        node.token_count = counted.tokens
        mode = counted.mode
    return mode


def clear_tokenizer_cache() -> None:
    _resolve_encoder.cache_clear()
