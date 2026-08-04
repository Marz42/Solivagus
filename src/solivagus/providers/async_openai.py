"""Async OpenAI-compatible chat via httpx."""

from __future__ import annotations

import json
from typing import Any

import httpx

from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    build_chat_endpoint,
    parse_chat_response,
)


async def call_chat_api_async(
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
    client: httpx.AsyncClient | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    endpoint = build_chat_endpoint(api_base)
    if messages is not None:
        payload_messages = messages
    else:
        if system_prompt is None or user_prompt is None:
            raise ProviderError("call_chat_api_async requires messages= or system_prompt+user_prompt")
        payload_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    payload: dict[str, Any] = {"model": model, "messages": payload_messages}
    if user_id:
        payload["user"] = user_id
    if send_temperature:
        payload["temperature"] = temperature
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await http.post(endpoint, headers=headers, content=json.dumps(payload))
        http_status = response.status_code
        body = response.text
        if http_status >= 400:
            detail = body[:800]
            if http_status in {400, 401, 402, 403, 404, 413, 422}:
                raise FatalProviderError(f"HTTP {http_status}: {detail}")
            raise ProviderError(f"HTTP {http_status}: {detail}")
        parsed = response.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"network error: {exc}") from exc
    finally:
        if owns_client:
            await http.aclose()

    if not isinstance(parsed, dict):
        raise ProviderError("response JSON must be an object")
    text, finish_reason, usage = parse_chat_response(parsed)
    usage = dict(usage)
    usage["http_status"] = http_status
    return text, finish_reason, usage


def is_rate_limited_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "http 429" in text or "insufficient_system_resource" in text or "http 503" in text
