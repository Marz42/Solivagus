"""Rolling output-token ratio calibration (brief §21.2)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from solivagus.util.text import atomic_write_json
from solivagus.workspace import workspace_root

DEFAULT_RATIO = 1.3
DEFAULT_OVERHEAD = 512
MIN_SAMPLES_FOR_P90 = 5
SAFETY_FACTOR = 1.2
MINIMUM_OUTPUT_TOKENS = 256
MAXIMUM_OUTPUT_TOKENS = 32_000
MODEL_OUTPUT_LIMIT = 64_000


@dataclass
class OutputCalibration:
    """Tracks completion_tokens / source_tokens samples and rolling P90."""

    ratios: list[float] = field(default_factory=list)
    max_samples: int = 200

    def record(self, *, source_tokens: int, completion_tokens: int) -> None:
        if source_tokens <= 0 or completion_tokens < 0:
            return
        ratio = completion_tokens / source_tokens
        if not math.isfinite(ratio) or ratio <= 0:
            return
        # Clamp absurd outliers before they poison P90.
        ratio = min(max(ratio, 0.2), 8.0)
        self.ratios.append(ratio)
        if len(self.ratios) > self.max_samples:
            self.ratios = self.ratios[-self.max_samples :]

    @property
    def sample_count(self) -> int:
        return len(self.ratios)

    def rolling_p90(self) -> float | None:
        if len(self.ratios) < MIN_SAMPLES_FOR_P90:
            return None
        ordered = sorted(self.ratios)
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

    def to_dict(self) -> dict:
        return {
            "ratios": list(self.ratios),
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
        raw = data.get("ratios") or []
        cleaned: list[float] = []
        for value in raw:
            try:
                ratio = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(ratio) and ratio > 0:
                cleaned.append(min(max(ratio, 0.2), 8.0))
        cal.ratios = cleaned[-cal.max_samples :]
        return cal


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
