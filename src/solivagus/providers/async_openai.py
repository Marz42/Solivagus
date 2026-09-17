"""Async OpenAI-compatible chat via httpx."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx

from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    _client_headers,
    _should_send_thinking,
    build_chat_endpoint,
    parse_chat_response,
    parse_retry_after,
)
from solivagus.providers.request_log import record_provider_request


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
    record_provider_request(
        kind="chat_async",
        model=model,
        endpoint=endpoint,
        user_id=user_id,
    )
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
    if disable_thinking and _should_send_thinking(api_base):
        payload["thinking"] = {"type": "disabled"}

    headers = _client_headers(api_key=api_key, session_id=user_id)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await http.post(endpoint, headers=headers, content=json.dumps(payload))
        http_status = response.status_code
        body = response.text
        if http_status >= 400:
            detail = body[:800]
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            if http_status in {400, 401, 402, 403, 404, 413, 422}:
                raise FatalProviderError(f"HTTP {http_status}: {detail}")
            raise ProviderError(f"HTTP {http_status}: {detail}", retry_after=retry_after)
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


async def backoff_sleep(attempt: int, exc: BaseException | None = None) -> None:
    """Prefer Retry-After; else exponential backoff + small jitter (brief §19.2)."""
    ra = retry_after_seconds(exc) if exc is not None else None
    if ra is not None and ra > 0:
        delay = float(ra) + random.uniform(0.0, 0.5)
    else:
        delay = min(2 ** max(0, attempt - 1), 8) + random.uniform(0.0, 0.25)
    await asyncio.sleep(delay)


def is_rate_limited_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "http 429" in text or "insufficient_system_resource" in text or "http 503" in text


def is_service_unavailable_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "http 503" in text or "insufficient_system_resource" in text


def retry_after_seconds(exc: BaseException) -> float | None:
    return getattr(exc, "retry_after", None)
