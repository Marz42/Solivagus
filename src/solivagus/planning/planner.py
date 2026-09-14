"""Planning orchestrator: parse → units → partitions → artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from solivagus.planning.cost_estimator import CostEstimate, PriceProfile, estimate_cost
from solivagus.planning.partition_builder import PartitionBudget, PlannedPartition, build_cache_partitions
from solivagus.planning.tokenizer import TokenCounter, annotate_node_tokens
from solivagus.planning.unit_builder import PlannedUnit, UnitBudget, build_translation_units
from solivagus.structure.parser import parse_markdown_structure
from solivagus.util.text import atomic_write_json, sha256_text


@dataclass
class PlanningConfig:
    unit_target_tokens: int = 12_000
    unit_max_tokens: int = 24_000
    unit_min_tokens: int = 1_500
    first_partition_tokens: int = 96_000
    partition_target_tokens: int = 220_000
    partition_max_tokens: int = 300_000
    cache_hit_per_million: float = 0.02
    cache_miss_per_million: float = 1.00
    output_per_million: float = 2.00

    def config_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return sha256_text(payload)[:16]

    def input_hash(self, calibration_fingerprint: dict[str, Any] | None = None) -> str:
        payload = {
            "config_hash": self.config_hash(),
            "calibration": calibration_fingerprint or {
                "schema": 2,
                "bucket": "none",
                "sample_count": 0,
                "rolling_p90": None,
            },
        }
        return sha256_text(json.dumps(payload, sort_keys=True, default=str))[:16]


@dataclass
class PlanResult:
    nodes: list
    units: list[PlannedUnit]
    partitions: list[PlannedPartition]
    cost: CostEstimate
    token_mode: str
    config_hash: str
    source_tokens: int
    input_hash: str = ""
    calibration: dict[str, Any] | None = None


def plan_from_markdown(
    markdown: str,
    config: PlanningConfig | None = None,
    *,
    calibration: Any | None = None,
) -> PlanResult:
    config = config or PlanningConfig()
    nodes = parse_markdown_structure(markdown)
    counter = TokenCounter()
    token_mode = annotate_node_tokens(nodes, counter)
    if calibration is not None:
        estimate_output_fn = calibration.estimate_output_tokens
    else:
        estimate_output_fn = None
    units = build_translation_units(
        nodes,
        budget=UnitBudget(
            target_tokens=config.unit_target_tokens,
            max_tokens=config.unit_max_tokens,
            min_tokens=config.unit_min_tokens,
        ),
        count_fn=lambda text: counter.count(text).tokens,
        estimate_output_fn=estimate_output_fn,
    )
    partitions = build_cache_partitions(
        units,
        budget=PartitionBudget(
            first_target_tokens=config.first_partition_tokens,
            target_tokens=config.partition_target_tokens,
            max_tokens=config.partition_max_tokens,
        ),
    )
    cost = estimate_cost(
        units,
        partitions,
        price=PriceProfile(
            cache_hit_per_million=config.cache_hit_per_million,
            cache_miss_per_million=config.cache_miss_per_million,
            output_per_million=config.output_per_million,
        ),
        mode=token_mode.value,
    )
    source_tokens = sum(n.token_count for n in nodes)
    cal_fp = None
    if calibration is not None and hasattr(calibration, "fingerprint"):
        cal_fp = calibration.fingerprint()
    config_hash = config.config_hash()
    return PlanResult(
        nodes=nodes,
        units=units,
        partitions=partitions,
        cost=cost,
        token_mode=token_mode.value,
        config_hash=config_hash,
        source_tokens=source_tokens,
        input_hash=config.input_hash(cal_fp),
        calibration=cal_fp,
    )


def write_plan_artifacts(artifact_dir: Path, plan: PlanResult) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    units_dir = artifact_dir / "units"
    partitions_dir = artifact_dir / "partitions"
    units_dir.mkdir(parents=True, exist_ok=True)
    partitions_dir.mkdir(parents=True, exist_ok=True)

    # Clear previous unit/partition files so OCR char-seeds do not linger.
    for path in units_dir.glob("*.source.md"):
        path.unlink(missing_ok=True)
    for path in partitions_dir.glob("p*.json"):
        path.unlink(missing_ok=True)

    unit_files: list[str] = []
    for unit in plan.units:
        rel = f"units/{unit.unit_key}.source.md"
        (artifact_dir / rel).write_text(unit.source_text, encoding="utf-8", newline="\n")
        unit_files.append(rel)

    for part in plan.partitions:
        payload = {
            "sequence_index": part.sequence_index,
            "unit_keys": part.unit_keys,
            "source_tokens": part.source_tokens,
            "unit_count": part.unit_count,
            "status": part.status,
        }
        atomic_write_json(partitions_dir / f"p{part.sequence_index:02d}.json", payload)

    report = {
        "config_hash": plan.config_hash,
        "input_hash": getattr(plan, "input_hash", plan.config_hash),
        "calibration": getattr(plan, "calibration", None),
        "token_mode": plan.token_mode,
        "source_tokens": plan.source_tokens,
        "unit_count": len(plan.units),
        "partition_count": len(plan.partitions),
        "cost": {
            "cache_miss_tokens": plan.cost.cache_miss_tokens,
            "cache_hit_tokens": plan.cost.cache_hit_tokens,
            "output_tokens": plan.cost.output_tokens,
            "estimated_cost": plan.cost.estimated_cost,
            "currency": plan.cost.currency,
            "mode": plan.cost.mode,
        },
        "units": [
            {
                "unit_key": u.unit_key,
                "source_tokens": u.source_tokens,
                "heading_path": u.heading_path,
                "source_file": f"units/{u.unit_key}.source.md",
            }
            for u in plan.units
        ],
        "partitions": [
            {
                "sequence_index": p.sequence_index,
                "unit_keys": p.unit_keys,
                "source_tokens": p.source_tokens,
            }
            for p in plan.partitions
        ],
    }
    atomic_write_json(artifact_dir / "plan-report.json", report)
    return report
