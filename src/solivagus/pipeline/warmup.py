"""Partition warm-up and cache probe decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable


class ProbeDecision(StrEnum):
    FULL = "full"
    LOW = "low"
    DEGRADED = "degraded"


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


def evaluate_probe(
    *,
    hit_tokens: int,
    expected_tokens: int,
    min_ratio: float = 0.70,
    warn_ratio: float = 0.50,
) -> ProbeDecision:
    if expected_tokens <= 0:
        return ProbeDecision.DEGRADED
    ratio = hit_tokens / expected_tokens
    if ratio >= min_ratio:
        return ProbeDecision.FULL
    if ratio >= warn_ratio:
        return ProbeDecision.LOW
    return ProbeDecision.DEGRADED


@dataclass
class WarmupResult:
    warmup_assistant: str
    prefix_hash: str
    user_id: str


def run_partition_warmup(
    *,
    chat_fn: ChatFn,
    settings: Any,
    stable_system: str,
    stable_user: str,
    prefix_hash: str,
    user_id: str,
) -> WarmupResult:
    import time

    text, _finish, _usage = chat_fn(
        api_base=settings.llm_api_base,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": stable_system},
            {"role": "user", "content": stable_user},
        ],
        user_id=user_id,
        temperature=settings.temperature,
        send_temperature=settings.send_temperature,
        timeout=settings.timeout_seconds,
        disable_thinking=True,
    )
    settle = float(getattr(settings, "cache_settle_seconds", 0.0) or 0.0)
    if settle > 0:
        time.sleep(settle)
    warmup_assistant = (text or "").strip() or "PARTITION_READY"
    return WarmupResult(
        warmup_assistant=warmup_assistant,
        prefix_hash=prefix_hash,
        user_id=user_id,
    )
