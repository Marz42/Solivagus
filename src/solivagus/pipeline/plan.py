"""Plan stage: structure tree + token/partition planning persisted to SQLite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solivagus.config import Settings
from solivagus.database import Database, utc_now
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.providers.prompts import document_user_id
from solivagus.planning.planner import PlanningConfig, plan_from_markdown, write_plan_artifacts
from solivagus.util.text import sha256_text


class PlanStageError(RuntimeError):
    pass


def planning_config_from_settings(settings: Settings) -> PlanningConfig:
    return PlanningConfig(
        unit_target_tokens=settings.unit_target_tokens,
        unit_max_tokens=settings.unit_max_tokens,
        unit_min_tokens=settings.unit_min_tokens,
        first_partition_tokens=settings.first_partition_tokens,
        partition_target_tokens=settings.partition_target_tokens,
        partition_max_tokens=settings.partition_max_tokens,
        cache_hit_per_million=settings.price_cache_hit_per_million,
        cache_miss_per_million=settings.price_cache_miss_per_million,
        output_per_million=settings.price_output_per_million,
    )


def _structure_plan_key(*, config_hash: str, source_hash: str) -> str:
    """Stable plan identity: planning knobs + source.md, not live calibration."""
    return f"plan:{config_hash}:{source_hash[:16]}"


def _preserve_unit_fields(existing: Any | None) -> dict[str, Any]:
    if existing is None:
        return {}
    status = str(existing["status"] or "")
    translation = existing["translation_text"]
    if status not in {UnitStatus.DONE.value, UnitStatus.FALLBACK.value} or not translation:
        return {}
    return {
        "status": status,
        "translation_text": translation,
        "translation_hash": existing["translation_hash"],
        "provider": existing["provider"],
        "model": existing["model"],
        "prompt_version": existing["prompt_version"],
        "style_capsule_version": existing["style_capsule_version"],
        "attempt_count": existing["attempt_count"] or 0,
        "warning_flags": existing["warning_flags"],
        "translated_file": existing["translated_file"],
    }


def run_plan_stage(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    force: bool = False,
) -> dict[str, Any]:
    doc = db.fetchone("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise PlanStageError(f"document not found: {document_id}")

    artifact_dir = Path(doc["artifact_dir"])
    source_path = artifact_dir / "source.md"
    if not source_path.is_file():
        raise PlanStageError(
            f"missing source.md under {artifact_dir}; run OCR stage first"
        )

    config = planning_config_from_settings(settings)
    from solivagus.planning.calibration import (
        calibration_bucket_key,
        load_calibration,
    )
    from solivagus.planning.tokenizer import TokenCounter

    calibration = load_calibration(settings.workspace)
    calibration.use_bucket(
        calibration_bucket_key(
            model=settings.llm_model,
            target_language=settings.target_language,
            tokenizer_mode=TokenCounter().mode.value,
        )
    )
    cal_fp = calibration.fingerprint()
    config_hash = config.config_hash()
    markdown = source_path.read_text(encoding="utf-8")
    source_hash = sha256_text(markdown)
    structure_key = _structure_plan_key(config_hash=config_hash, source_hash=source_hash)
    existing_hash = str(doc["active_config_hash"] or "")
    has_partitions = bool(db.list_partitions(document_id))
    has_nodes = bool(db.list_structural_nodes(document_id))
    # Only the source-aware key is idempotent. Legacy plan:{config_hash} always
    # replans so a changed source.md cannot be silently upgraded into a new key.
    if (
        not force
        and has_partitions
        and has_nodes
        and existing_hash == structure_key
    ):
        units = db.list_units(document_id)
        partitions = db.list_partitions(document_id)
        report_path = artifact_dir / "plan-report.json"
        return {
            "document_id": document_id,
            "skipped": True,
            "reason": "plan_idempotent_hit",
            "unit_count": len(units),
            "partition_count": len(partitions),
            "config_hash": config_hash,
            "input_hash": config_hash,
            "structure_key": structure_key,
            "calibration": cal_fp,
            "plan_report": str(report_path) if report_path.is_file() else None,
        }

    db.update_document_status(
        document_id,
        status=DocumentStatus.PLANNING.value,
        translation_status="planning",
    )

    plan = plan_from_markdown(markdown, config, calibration=calibration)
    report = write_plan_artifacts(artifact_dir, plan)

    node_rows = [
        {
            "temp_id": node.temp_id,
            "parent_temp_id": node.parent_temp_id,
            "node_type": node.node_type.value,
            "sequence_index": node.sequence_index,
            "heading_level": node.heading_level,
            "heading_path": node.heading_path,
            "source_pages": node.source_pages,
            "source_text": node.source_text,
            "source_hash": node.source_hash or sha256_text(node.source_text),
            "token_count": node.token_count,
            "metadata_json": json.dumps(node.metadata, ensure_ascii=False)
            if node.metadata
            else None,
        }
        for node in plan.nodes
    ]
    db.replace_structural_nodes(document_id, node_rows)

    user_id = document_user_id(str(doc["source_sha256"]))
    partition_rows = [
        {
            "sequence_index": p.sequence_index,
            "source_tokens": p.source_tokens,
            "context_tokens": 0,
            "unit_count": p.unit_count,
            "prefix_hash": None,
            "user_id": user_id,
            "warmup_status": "pending",
            "expected_cache_tokens": p.source_tokens,
            "actual_probe_hit_tokens": None,
            "status": p.status,
            "unit_keys": p.unit_keys,
        }
        for p in plan.partitions
    ]
    # Capture completed work before partition/unit replacement.
    previous_units = db.list_units(document_id)
    previous_by_hash = {
        str(u["source_hash"]): u for u in previous_units if u["source_hash"]
    }
    previous_by_key = {str(u["unit_key"]): u for u in previous_units}

    # Old capsules bind to prior partition ids / plan generations — drop them.
    db.clear_style_capsules(document_id)
    capsule_dir = artifact_dir / "style_capsules"
    if capsule_dir.is_dir():
        for path in capsule_dir.glob("v*.json"):
            path.unlink(missing_ok=True)

    partition_ids = db.replace_partitions(document_id, partition_rows)
    key_to_partition_id: dict[str, int] = {}
    for part, part_id in zip(plan.partitions, partition_ids, strict=True):
        for key in part.unit_keys:
            key_to_partition_id[key] = part_id

    unit_rows = []
    preserved = 0
    for unit in plan.units:
        prev = previous_by_hash.get(unit.source_hash) or previous_by_key.get(unit.unit_key)
        if prev is not None and str(prev["source_hash"] or "") != unit.source_hash:
            prev = None
        kept = _preserve_unit_fields(prev)
        if kept:
            preserved += 1
        unit_rows.append(
            {
                "unit_key": unit.unit_key,
                "sequence_index": unit.sequence_index,
                "partition_id": key_to_partition_id.get(unit.unit_key),
                "heading_path": unit.heading_path,
                "source_text": unit.source_text,
                "source_hash": unit.source_hash,
                "source_tokens": unit.source_tokens,
                "estimated_output_tokens": unit.estimated_output_tokens,
                "status": kept.get("status", UnitStatus.PENDING.value),
                "translation_text": kept.get("translation_text"),
                "translation_hash": kept.get("translation_hash"),
                "provider": kept.get("provider"),
                "model": kept.get("model"),
                "prompt_version": kept.get("prompt_version"),
                "style_capsule_version": kept.get("style_capsule_version"),
                "attempt_count": kept.get("attempt_count", 0),
                "warning_flags": kept.get("warning_flags"),
                "source_file": f"units/{unit.unit_key}.source.md",
                "translated_file": kept.get("translated_file"),
            }
        )
    db.replace_units(document_id, unit_rows)

    db.execute(
        """
        UPDATE documents SET
          active_config_hash = ?,
          status = ?,
          translation_status = ?,
          updated_at = ?
        WHERE id = ?
        """,
        (
            structure_key,
            DocumentStatus.PLANNING.value,
            "planned",
            utc_now(),
            document_id,
        ),
    )
    db.record_artifact(
        document_id,
        "plan_report",
        str(artifact_dir / "plan-report.json"),
        content_hash=sha256_text(json.dumps(report, sort_keys=True)),
    )
    db.commit()

    return {
        "document_id": document_id,
        "skipped": False,
        "unit_count": len(plan.units),
        "partition_count": len(plan.partitions),
        "node_count": len(plan.nodes),
        "source_tokens": plan.source_tokens,
        "token_mode": plan.token_mode,
        "config_hash": config_hash,
        "input_hash": config_hash,
        "structure_key": structure_key,
        "calibration": cal_fp,
        "preserved_units": preserved,
        "estimated_cost": plan.cost.estimated_cost,
        "currency": plan.cost.currency,
        "cache_miss_tokens": plan.cost.cache_miss_tokens,
        "cache_hit_tokens": plan.cost.cache_hit_tokens,
        "output_tokens": plan.cost.output_tokens,
        "plan_report": str(artifact_dir / "plan-report.json"),
    }
