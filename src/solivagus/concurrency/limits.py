"""Async concurrency gates with adaptive 429 backoff."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class ConcurrencyConfig:
    global_limit: int = 16
    per_document_limit: int = 8
    per_partition_limit: int = 8
    max_global_limit: int = 64
    low_probe_limit: int = 2
    adaptive: bool = True


class ConcurrencyGate:
    """Dynamic concurrency limit; `halve()` shrinks the limit after 429."""

    def __init__(self, limit: int, *, minimum: int = 1) -> None:
        self._limit = max(minimum, limit)
        self._minimum = minimum
        self._active = 0
        self._condition = asyncio.Condition()
        self.success_streak = 0

    @property
    def limit(self) -> int:
        return self._limit

    async def acquire(self) -> None:
        async with self._condition:
            while self._active >= self._limit:
                await self._condition.wait()
            self._active += 1

    async def release(self) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    async def record_success(self, *, adaptive: bool, bump_every: int = 30) -> None:
        if not adaptive:
            return
        async with self._condition:
            self.success_streak += 1
            if self.success_streak >= bump_every:
                self.success_streak = 0
                self._limit += 2
                self._condition.notify_all()

    async def record_rate_limit(self, *, adaptive: bool) -> None:
        async with self._condition:
            self.success_streak = 0
            if adaptive:
                self._limit = max(self._minimum, self._limit // 2)
            self._condition.notify_all()


class NestedGates:
    """Acquire global → document → partition gates in order."""

    def __init__(
        self,
        global_gate: ConcurrencyGate,
        document_gate: ConcurrencyGate,
        partition_gate: ConcurrencyGate,
    ) -> None:
        self.global_gate = global_gate
        self.document_gate = document_gate
        self.partition_gate = partition_gate

    async def __aenter__(self) -> NestedGates:
        await self.global_gate.acquire()
        try:
            await self.document_gate.acquire()
            try:
                await self.partition_gate.acquire()
            except BaseException:
                await self.document_gate.release()
                raise
        except BaseException:
            await self.global_gate.release()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.partition_gate.release()
        await self.document_gate.release()
        await self.global_gate.release()


def partition_limit_for_probe(
    decision: str,
    config: ConcurrencyConfig,
) -> int:
    if decision == "degraded":
        return 1
    if decision == "low":
        return max(1, config.low_probe_limit)
    return max(1, config.per_partition_limit)
