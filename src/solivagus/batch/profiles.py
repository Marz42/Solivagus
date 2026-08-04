"""Named concurrency / OCR profiles for overnight batch runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from solivagus.config import Settings

ProfileName = Literal["conservative", "balanced", "throughput"]


@dataclass(frozen=True)
class BatchProfile:
    name: ProfileName
    global_concurrency: int
    per_document_concurrency: int
    per_partition_concurrency: int
    ocr_workers: int
    translate_workers: int
    adaptive_concurrency: bool
    continue_on_error: bool
    prevent_sleep: bool


PROFILES: dict[str, BatchProfile] = {
    "conservative": BatchProfile(
        name="conservative",
        global_concurrency=8,
        per_document_concurrency=4,
        per_partition_concurrency=4,
        ocr_workers=1,
        translate_workers=1,
        adaptive_concurrency=True,
        continue_on_error=True,
        prevent_sleep=True,
    ),
    "balanced": BatchProfile(
        name="balanced",
        global_concurrency=16,
        per_document_concurrency=8,
        per_partition_concurrency=8,
        ocr_workers=1,
        translate_workers=2,
        adaptive_concurrency=True,
        continue_on_error=True,
        prevent_sleep=True,
    ),
    "throughput": BatchProfile(
        name="throughput",
        global_concurrency=32,
        per_document_concurrency=8,
        per_partition_concurrency=8,
        ocr_workers=1,
        translate_workers=4,
        adaptive_concurrency=True,
        continue_on_error=True,
        prevent_sleep=True,
    ),
}


def get_profile(name: str) -> BatchProfile:
    key = (name or "balanced").strip().lower()
    if key not in PROFILES:
        raise ValueError(
            f"unknown profile {name!r}; expected one of {', '.join(sorted(PROFILES))}"
        )
    return PROFILES[key]


def apply_profile(settings: Settings, profile: BatchProfile | str) -> BatchProfile:
    """Mutate settings concurrency knobs to match a named profile; return profile."""
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    settings.global_concurrency = resolved.global_concurrency
    settings.per_document_concurrency = resolved.per_document_concurrency
    settings.per_partition_concurrency = resolved.per_partition_concurrency
    settings.adaptive_concurrency = resolved.adaptive_concurrency
    settings.max_global_concurrency = max(
        settings.max_global_concurrency, resolved.global_concurrency
    )
    return resolved
