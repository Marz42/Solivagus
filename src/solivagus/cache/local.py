"""Local content-addressed translation cache."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from solivagus.util.text import atomic_write_json, sha256_text

logger = logging.getLogger(__name__)


def translation_cache_key(
    *,
    source_text: str,
    provider: str,
    model: str,
    prompt_version: str,
    target_language: str,
    glossary_hash: str = "",
    style_capsule_hash: str = "",
    translation_parameters: str = "",
) -> str:
    payload = "".join(
        [
            source_text,
            provider,
            model,
            prompt_version,
            target_language,
            glossary_hash,
            style_capsule_hash,
            translation_parameters,
        ]
    )
    return sha256_text(payload)


def cache_path(cache_root: Path, key: str) -> Path:
    return cache_root / key[:2] / f"{key}.json"


def load_translation(cache_root: Path, key: str) -> dict[str, Any] | None:
    path = cache_path(cache_root, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("corrupt translation cache ignored: %s (%s)", path, exc)
        return None
    if not isinstance(data, dict) or not data.get("translation_text"):
        logger.warning("invalid translation cache ignored: %s", path)
        return None
    return data


def store_translation(cache_root: Path, key: str, payload: dict[str, Any]) -> None:
    path = cache_path(cache_root, key)
    try:
        atomic_write_json(path, payload)
    except OSError as exc:
        logger.warning("failed to write translation cache %s: %s", path, exc)
