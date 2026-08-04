"""HTML table cell translator — structure-preserving refill.

Default mode keeps tables verbatim. ``translate_cells`` extracts cell text,
requests JSON translations, then refills the original tag skeleton.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal

from solivagus.providers.openai_compatible import ProviderError

ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]

HtmlTableMode = Literal["keep", "translate_cells"]

_CELL_RE = re.compile(
    r"(<(?:td|th)\b[^>]*>)(.*?)(</(?:td|th)>)",
    re.DOTALL | re.IGNORECASE,
)

_TABLE_SYSTEM = (
    "你是技术文献表格翻译器。只翻译单元格自然语言文本，"
    "保留数字、单位、符号与专有名词写法。"
    "只输出 JSON 数组，元素与输入一一对应，不要解释。"
)


def extract_cell_texts(html: str) -> list[str]:
    return [m.group(2) for m in _CELL_RE.finditer(html or "")]


def refill_table_cells(html: str, translations: list[str]) -> str:
    """Replace cell inner HTML in document order; tags/attributes unchanged."""
    texts = list(translations)
    index = 0

    def _repl(match: re.Match[str]) -> str:
        nonlocal index
        if index >= len(texts):
            return match.group(0)
        open_tag, _old, close_tag = match.group(1), match.group(2), match.group(3)
        new_inner = texts[index]
        index += 1
        return f"{open_tag}{new_inner}{close_tag}"

    return _CELL_RE.sub(_repl, html)


def _parse_json_list(raw: str, expected: int) -> list[str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ProviderError("table translator expected a JSON array")
    if len(data) != expected:
        raise ProviderError(
            f"table translator length mismatch: got {len(data)} expected {expected}"
        )
    return ["" if item is None else str(item) for item in data]


def translate_html_table(
    html: str,
    *,
    mode: HtmlTableMode = "keep",
    chat_fn: ChatFn | None = None,
    api_base: str = "",
    api_key: str | None = None,
    model: str = "",
    timeout: int = 300,
    send_temperature: bool = True,
) -> str:
    """Translate table cell text while preserving HTML structure, or keep as-is."""
    if mode == "keep" or not html:
        return html
    if chat_fn is None:
        raise ProviderError("translate_cells mode requires chat_fn")

    cells = extract_cell_texts(html)
    if not cells:
        return html

    # Skip pure-whitespace / numeric-only cells in the prompt? Keep all for index fidelity.
    user_prompt = (
        "将下列表格单元格文本译为简体中文。返回等长 JSON 字符串数组。\n\n"
        + json.dumps(cells, ensure_ascii=False)
    )
    raw, finish_reason, _usage = chat_fn(
        api_base=api_base,
        api_key=api_key,
        model=model,
        system_prompt=_TABLE_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.0,
        send_temperature=send_temperature,
        timeout=timeout,
        disable_thinking=True,
    )
    if finish_reason and finish_reason != "stop":
        raise ProviderError(f"table translator finish_reason={finish_reason}")
    translations = _parse_json_list(raw, len(cells))
    return refill_table_cells(html, translations)


def translate_html_tables_in_markdown(
    markdown: str,
    *,
    mode: HtmlTableMode = "keep",
    chat_fn: ChatFn | None = None,
    **kwargs: Any,
) -> str:
    """Apply table translation to every <table>…</table> in markdown."""
    if mode == "keep":
        return markdown
    table_re = re.compile(r"<table\b[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)

    def _one(match: re.Match[str]) -> str:
        return translate_html_table(
            match.group(0), mode=mode, chat_fn=chat_fn, **kwargs
        )

    return table_re.sub(_one, markdown)
