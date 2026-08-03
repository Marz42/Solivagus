"""Write usage-report.json for a translation run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from solivagus.util.text import atomic_write_json


def write_usage_report(artifact_dir: Path, report: dict[str, Any]) -> Path:
    path = artifact_dir / "usage-report.json"
    atomic_write_json(path, report)
    return path


def empty_usage_totals() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "completion_tokens": 0,
        "api_calls": 0,
        "local_cache_hits": 0,
    }


def add_usage(totals: dict[str, int], usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    totals["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    totals["cache_hit_tokens"] += int(
        usage.get("prompt_cache_hit_tokens") or usage.get("cache_hit_tokens") or 0
    )
    totals["cache_miss_tokens"] += int(
        usage.get("prompt_cache_miss_tokens") or usage.get("cache_miss_tokens") or 0
    )
    totals["completion_tokens"] += int(usage.get("completion_tokens") or 0)
    totals["api_calls"] += 1
