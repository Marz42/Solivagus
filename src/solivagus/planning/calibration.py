"""Rolling output-token ratio calibration (brief §21.2)."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from solivagus.util.text import atomic_write_json, sha256_text
from solivagus.workspace import workspace_root

DEFAULT_RATIO = 1.3
DEFAULT_OVERHEAD = 512
MIN_SAMPLES_FOR_P90 = 5
SAFETY_FACTOR = 1.2
MINIMUM_OUTPUT_TOKENS = 256
MAXIMUM_OUTPUT_TOKENS = 32_000
MODEL_OUTPUT_LIMIT = 64_000
CALIBRATION_SCHEMA = 2
DEFAULT_BUCKET = "default"

_PROCESS_LOCK = threading.Lock()


def calibration_bucket_key(
    *,
    model: str,
    target_language: str,
    tokenizer_mode: str,
) -> str:
    return f"{model}|{target_language}|{tokenizer_mode}"


@dataclass
class OutputCalibration:
    """Tracks completion_tokens / source_tokens samples and rolling P90."""

    buckets: dict[str, list[float]] = field(default_factory=dict)
    max_samples: int = 200
    active_key: str = DEFAULT_BUCKET

    def use_bucket(self, key: str) -> None:
        self.active_key = key or DEFAULT_BUCKET
        self.buckets.setdefault(self.active_key, [])

    def _ratios(self) -> list[float]:
        return self.buckets.setdefault(self.active_key, [])

    def record(self, *, source_tokens: int, completion_tokens: int) -> None:
        if source_tokens <= 0 or completion_tokens < 0:
            return
        ratio = completion_tokens / source_tokens
        if not math.isfinite(ratio) or ratio <= 0:
            return
        # Clamp absurd outliers before they poison P90.
        ratio = min(max(ratio, 0.2), 8.0)
        ratios = self._ratios()
        ratios.append(ratio)
        if len(ratios) > self.max_samples:
            self.buckets[self.active_key] = ratios[-self.max_samples :]

    @property
    def sample_count(self) -> int:
        return len(self._ratios())

    def rolling_p90(self) -> float | None:
        ratios = self._ratios()
        if len(ratios) < MIN_SAMPLES_FOR_P90:
            return None
        ordered = sorted(ratios)
        # Nearest-rank P90.
        idx = max(0, min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1))
        return ordered[idx]

    def estimate_output_tokens(
        self,
        source_tokens: int,
        *,
        minimum: int = MINIMUM_OUTPUT_TOKENS,
        maximum: int = MAXIMUM_OUTPUT_TOKENS,
        model_limit: int = MODEL_OUTPUT_LIMIT,
    ) -> int:
        source_tokens = max(0, int(source_tokens))
        p90 = self.rolling_p90()
        if p90 is None:
            estimate = int(source_tokens * DEFAULT_RATIO) + DEFAULT_OVERHEAD
        else:
            estimate = int(source_tokens * p90 * SAFETY_FACTOR)
        estimate = max(minimum, estimate)
        estimate = min(maximum, estimate, model_limit)
        return estimate

    def fingerprint(self) -> dict:
        p90 = self.rolling_p90()
        return {
            "schema": CALIBRATION_SCHEMA,
            "bucket": self.active_key,
            "sample_count": self.sample_count,
            "rolling_p90": p90,
        }

    def fingerprint_hash(self) -> str:
        payload = json.dumps(self.fingerprint(), sort_keys=True, default=str)
        return sha256_text(payload)[:16]

    def to_dict(self) -> dict:
        active = self._ratios()
        return {
            "schema": CALIBRATION_SCHEMA,
            "active_bucket": self.active_key,
            "buckets": {key: list(values) for key, values in self.buckets.items()},
            "ratios": list(active),
            "sample_count": self.sample_count,
            "rolling_p90": self.rolling_p90(),
            "default_ratio": DEFAULT_RATIO,
            "safety_factor": SAFETY_FACTOR,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> OutputCalibration:
        cal = cls()
        if not data:
            return cal
        buckets: dict[str, list[float]] = {}
        raw_buckets = data.get("buckets")
        if isinstance(raw_buckets, dict):
            for key, raw in raw_buckets.items():
                cleaned = _clean_ratios(raw)
                if cleaned:
                    buckets[str(key)] = cleaned[-cal.max_samples :]
        if not buckets:
            cleaned = _clean_ratios(data.get("ratios") or [])
            if cleaned:
                buckets[DEFAULT_BUCKET] = cleaned[-cal.max_samples :]
        cal.buckets = buckets
        active = str(data.get("active_bucket") or DEFAULT_BUCKET)
        if active not in cal.buckets:
            active = next(iter(cal.buckets), DEFAULT_BUCKET)
        cal.active_key = active
        cal.buckets.setdefault(cal.active_key, [])
        return cal


def _clean_ratios(raw: object) -> list[float]:
    if not isinstance(raw, list):
        return []
    cleaned: list[float] = []
    for value in raw:
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(ratio) and ratio > 0:
            cleaned.append(min(max(ratio, 0.2), 8.0))
    return cleaned


def calibration_path(workspace: Path) -> Path:
    return workspace_root(workspace) / "cache" / "output-calibration.json"


def load_calibration(workspace: Path) -> OutputCalibration:
    path = calibration_path(workspace)
    if not path.is_file():
        return OutputCalibration()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OutputCalibration()
    if not isinstance(data, dict):
        return OutputCalibration()
    return OutputCalibration.from_dict(data)


def save_calibration(workspace: Path, calibration: OutputCalibration) -> Path:
    path = calibration_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, calibration.to_dict())
    return path


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def record_calibration_sample(
    workspace: Path,
    *,
    source_tokens: int,
    completion_tokens: int,
    model: str,
    target_language: str,
    tokenizer_mode: str,
) -> OutputCalibration:
    """Read-merge-write one sample under a process + file lock."""
    key = calibration_bucket_key(
        model=model,
        target_language=target_language,
        tokenizer_mode=tokenizer_mode,
    )
    lock_path = calibration_path(workspace).with_name("output-calibration.lock")
    with _PROCESS_LOCK, _exclusive_file_lock(lock_path):
        cal = load_calibration(workspace)
        cal.use_bucket(key)
        cal.record(source_tokens=source_tokens, completion_tokens=completion_tokens)
        save_calibration(workspace, cal)
        return cal
