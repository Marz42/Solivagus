"""Normalized usage records from OpenAI-compatible responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UsageRecord:
    prompt_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    completion_tokens: int = 0
    http_status: int | None = None

    @classmethod
    def from_api(cls, usage: dict[str, Any] | None) -> UsageRecord:
        data = usage or {}
        hit = int(
            data.get("prompt_cache_hit_tokens")
            or data.get("cache_hit_tokens")
            or 0
        )
        miss = int(
            data.get("prompt_cache_miss_tokens")
            or data.get("cache_miss_tokens")
            or 0
        )
        prompt = int(data.get("prompt_tokens") or 0)
        if prompt == 0 and (hit or miss):
            prompt = hit + miss
        return cls(
            prompt_tokens=prompt,
            cache_hit_tokens=hit,
            cache_miss_tokens=miss,
            completion_tokens=int(data.get("completion_tokens") or 0),
            http_status=int(data["http_status"]) if data.get("http_status") is not None else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "prompt_cache_hit_tokens": self.cache_hit_tokens,
            "prompt_cache_miss_tokens": self.cache_miss_tokens,
            "completion_tokens": self.completion_tokens,
            "http_status": self.http_status,
        }
