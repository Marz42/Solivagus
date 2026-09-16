"""OpenAI-compatible chat provider (DeepSeek-first)."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from solivagus.providers.request_log import record_provider_request


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class FatalProviderError(ProviderError):
    pass


def parse_retry_after(header_value: str | None) -> float | None:
    """Parse Retry-After as seconds (delta-seconds only; HTTP-date ignored)."""
    if not header_value:
        return None
    text = str(header_value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        return None
    if seconds < 0 or seconds != seconds:  # NaN
        return None
    return min(seconds, 300.0)


SYSTEM_PROMPT = (
    "你是严谨的技术文献翻译器。你的唯一任务是忠实翻译，不做摘要、评论、解释或内容补写。"
)

USER_PROMPT_TEMPLATE = """请将下面的技术文献内容翻译为{target_language}。

硬性要求：
1. 完整翻译，不总结、不删减、不扩写，不添加原文没有的信息。
2. 保持 Markdown 标题、段落、列表、表格、引用和换行结构。
3. 所有形如 @@PRESERVE_00001@@ 的占位符必须原样保留，不能改写、删除、调序或加空格。
4. 保留章节号、图号、表号、参考文献编号、变量名、产品名、模型名和算法名。
5. 技术术语采用通行译法；重要术语首次出现可写作“中文译名（English term）”。
6. 严格保持原文证据强度，不把 may、might、suggest、associate、approximately 等不确定表达翻译成确定结论。
7. 只输出翻译后的 Markdown 正文，不要输出说明，不要使用包裹全文的代码围栏。

文档标题：{document_title}
当前翻译块：{block_id}

术语表（可能为空；如有则优先遵守）：
{glossary}

待翻译内容：
{protected_markdown}
"""


def build_chat_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def parse_chat_response(response: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    try:
        choice = response["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            "LLM API 返回格式不是 OpenAI-compatible chat/completions："
            + json.dumps(response, ensure_ascii=False)[:800]
        ) from exc

    text: str | None = None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            text = "".join(parts)
    if text is None:
        raise ProviderError("LLM API 返回的 message.content 不是可识别文本。")
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return text, finish_reason, usage


def call_chat_api(
    *,
    api_base: str,
    api_key: str | None,
    model: str,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
    temperature: float = 0.1,
    send_temperature: bool = True,
    timeout: int = 300,
    disable_thinking: bool = True,
) -> tuple[str, str | None, dict[str, Any]]:
    endpoint = build_chat_endpoint(api_base)
    record_provider_request(
        kind="chat",
        model=model,
        endpoint=endpoint,
        user_id=user_id,
    )
    if messages is not None:
        payload_messages = messages
    else:
        if system_prompt is None or user_prompt is None:
            raise ProviderError("call_chat_api requires messages= or system_prompt+user_prompt")
        payload_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    payload: dict[str, Any] = {
        "model": model,
        "messages": payload_messages,
    }
    if user_id:
        payload["user"] = user_id
    if send_temperature:
        payload["temperature"] = temperature
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            http_status = getattr(resp, "status", 200)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        retry_after = parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
        if exc.code in {400, 401, 402, 403, 404, 413, 422}:
            raise FatalProviderError(f"HTTP {exc.code}: {detail[:800]}") from exc
        raise ProviderError(
            f"HTTP {exc.code}: {detail[:800]}", retry_after=retry_after
        ) from exc
    except error.URLError as exc:
        raise ProviderError(f"network error: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"invalid JSON response: {body[:800]}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("response JSON must be an object")
    text, finish_reason, usage = parse_chat_response(parsed)
    usage = dict(usage)
    usage["http_status"] = http_status
    return text, finish_reason, usage
