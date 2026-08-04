"""Single-writer lock for SQLite mutations during async translation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class DbWriter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def run(self, fn: Callable[[], T]) -> T:
        async with self._lock:
            return fn()
