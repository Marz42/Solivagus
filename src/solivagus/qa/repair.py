"""Directed one-shot QA repair."""

from __future__ import annotations

from typing import Any, Callable

from solivagus.config import Settings
from solivagus.providers.openai_compatible import FatalProviderError, ProviderError
from solivagus.qa.models import QAFinding

ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]

REPAIR_SYSTEM = (
    "你是技术文献校对编辑。只修复列出的机械错误，不要重写其他内容，"
    "不要添加解释。只输出修复后的 Markdown 译文。"
)


def build_repair_prompt(
    *,
    source: str,
    translation: str,
    findings: list[QAFinding],
    unit_key: str,
) -> str:
    errors = "\n".join(
        f"- [{f.severity}] {f.message}" + (f"（{f.detail}）" if f.detail else "")
        for f in findings
    )
    return (
        f"Unit：{unit_key}\n\n"
        "只修复列出的问题，不要重新改写其他内容。\n\n"
        f"机械错误：\n{errors}\n\n"
        f"原文：\n{source}\n\n"
        f"当前译文：\n{translation}\n"
    )


def repair_unit(
    *,
    source: str,
    translation: str,
    findings: list[QAFinding],
    unit_key: str,
    settings: Settings,
    chat_fn: ChatFn,
) -> str:
    if not findings:
        return translation
    model = settings.repair_model or settings.llm_model
    user_prompt = build_repair_prompt(
        source=source,
        translation=translation,
        findings=findings,
        unit_key=unit_key,
    )
    raw, finish_reason, _usage = chat_fn(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=model,
        system_prompt=REPAIR_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.0,
        send_temperature=settings.send_temperature,
        timeout=settings.timeout_seconds,
        disable_thinking=True,
    )
    if finish_reason and finish_reason != "stop":
        raise ProviderError(f"repair finish_reason={finish_reason}")
    text = (raw or "").strip()
    if not text:
        raise ProviderError("repair returned empty text")
    return text if text.endswith("\n") else text + "\n"
