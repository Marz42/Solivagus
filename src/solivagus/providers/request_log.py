"""Append-only provider HTTP request log (warm-up / translate / repair / probe).

translation_attempts only covers unit translate calls. This log records every
call_chat_api / call_chat_api_async entry so soak can prove zero provider traffic
on re-run.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

_lock = threading.Lock()
_log_path: ContextVar[Path | None] = ContextVar("solivagus_provider_log_path", default=None)
_process_count = 0


def provider_request_count() -> int:
    with _lock:
        return _process_count


def reset_provider_request_count_for_tests() -> None:
    global _process_count
    with _lock:
        _process_count = 0


def set_provider_log_path(path: Path | None) -> None:
    _log_path.set(path)


def get_provider_log_path() -> Path | None:
    return _log_path.get()


@contextmanager
def provider_log_scope(path: Path | None) -> Iterator[None]:
    token = _log_path.set(path)
    try:
        yield
    finally:
        _log_path.reset(token)


def record_provider_request(
    *,
    kind: str = "chat",
    model: str | None = None,
    endpoint: str | None = None,
    user_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Count + optionally append one JSONL line. Safe to call from sync/async threads."""
    global _process_count
    path = _log_path.get()
    entry: dict[str, Any] = {
        "ts": time.time(),
        "kind": kind,
        "model": model,
        "endpoint": endpoint,
        "user_id": user_id,
    }
    if extra:
        entry.update(extra)
    with _lock:
        _process_count += 1
        entry["seq"] = _process_count
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def count_provider_log_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n
