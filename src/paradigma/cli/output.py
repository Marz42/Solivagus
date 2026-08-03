"""Text and JSON rendering for command outcomes."""

from __future__ import annotations

import json
import sys

from ..application.outcomes import CommandOutcome


def configure_utf8_stdio() -> None:
    """Make redirected CLI output deterministic on every supported platform."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            # In-memory and already-closed test streams may not be reconfigurable.
            continue


def render_json(outcome: CommandOutcome) -> str:
    return json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)


def render_text(outcome: CommandOutcome) -> str:
    lines = list(outcome.messages)
    if not outcome.ok:
        lines.extend(f"ERROR: {diagnostic.format()}" for diagnostic in outcome.diagnostics)
        return "\n".join(lines)
    if outcome.command == "version":
        lines.extend(f"{key}: {value}" for key, value in outcome.data.items())
    elif outcome.command == "config validate":
        lines.extend(
            (
                f"config_schema_version: {outcome.data['config_schema_version']}",
                "knowledge_roots: " + ", ".join(outcome.data["knowledge_roots"]),
                f"machine_index_path: {outcome.data['machine_index_path']}",
                f"runtime_root: {outcome.data['runtime_root']}",
                f"memory_root: {outcome.data['memory_root']}",
                f"catalog_path: {outcome.data['catalog_path']}",
            )
        )
    if outcome.command == "runtime verify":
        return "\n".join(
            (
                outcome.messages[0],
                f"current={str(outcome.data['current']).lower()}; "
                f"active_task={str(outcome.data['active_task_current']).lower()}; "
                f"handoff={str(outcome.data['handoff_current']).lower()}",
            )
        )
    if outcome.command == "runtime rebuild":
        return "\n".join(
            (
                outcome.messages[0],
                f"would_change={str(outcome.data['would_change']).lower()}; "
                f"written={str(outcome.data['written']).lower()}",
            )
        )
    if outcome.command == "runtime init" and outcome.ok:
        return "\n".join(
            (
                outcome.messages[0],
                f"would_change={str(outcome.data['would_change']).lower()}; "
                f"written={str(outcome.data['written']).lower()}",
            )
        )
    if outcome.command == "task status":
        if not outcome.data["active"]:
            return outcome.messages[0]
        task = outcome.data["task"]
        return "\n".join(
            (
                outcome.messages[0],
                f"task_id: {task['task_id']}",
                f"status: {task['status']}",
                f"revision: {task['snapshot_revision']}",
                f"source_hash: {task['source_hash']}",
            )
        )
    if outcome.command.startswith("task ") and outcome.command != "task archive":
        task = outcome.data["task"]
        return "\n".join(
            (
                outcome.messages[0],
                f"task_id: {task['task_id']}",
                f"status: {task['status']}",
                f"written: {str(outcome.data['written']).lower()}",
            )
        )
    if outcome.command == "session status":
        if not outcome.data["active"]:
            return outcome.messages[0]
        session = outcome.data["session"]
        return "\n".join(
            (
                outcome.messages[0],
                f"session_id: {session['session_id']}",
                f"task_id: {session['task_id']}",
                f"status: {session['status']}",
                f"checkpoint: {session['current_checkpoint_id'] or 'none'}",
            )
        )
    if outcome.command.startswith("session "):
        return "\n".join((outcome.messages[0], f"written: {str(outcome.data['written']).lower()}"))
    if outcome.command == "handoff build":
        return "\n".join(
            (outcome.messages[0], f"current={str(outcome.data['current']).lower()}")
        )
    if outcome.command == "context build" and outcome.ok:
        lines.extend(
            (
                f"checksum: {outcome.data['checksum']}",
                f"budget: {outcome.data['budget_tokens']}",
                f"estimated: {outcome.data['estimated_tokens']}",
                f"written: {str(outcome.data['written']).lower()}",
            )
        )
        for item in outcome.data["documents"]:
            lines.append(
                f"{item['priority'].upper()}: {item['path']} "
                f"({', '.join(item['reasons'])})"
            )
        for item in outcome.data["excluded"]:
            lines.append(f"EXCLUDED: {item['path']} ({item['reason']})")
        return "\n".join(lines)
    if outcome.command == "context verify" and outcome.ok:
        return "\n".join(
            (outcome.messages[0], f"current={str(outcome.data['current']).lower()}")
        )
    elif outcome.command == "index verify":
        for item in outcome.data["items"]:
            state = "OK" if item["current"] else "STALE"
            lines.append(f"{state}: {item['label']}: {item['path']}")
        lines.append(f"Verified derived indexes; stale={outcome.data['stale']}.")
    elif outcome.command == "index rebuild":
        action = "would_update" if outcome.dry_run else "updated"
        lines.append(
            f"concepts={outcome.data['concept_count']}; "
            f"{action}={outcome.data[action]}."
        )
        lines.extend(outcome.data["paths"])
    elif outcome.command == "catalog rebuild":
        action = "would write" if outcome.dry_run else "wrote"
        lines.append(
            f"{action} {outcome.data['catalog_path']}; "
            f"records={outcome.data['record_count']}; "
            f"source_digest={outcome.data['source_digest']}"
        )
    elif outcome.command == "catalog verify":
        lines.append(
            f"current={str(outcome.data['current']).lower()}; "
            f"source={outcome.data['source_count']}; "
            f"catalog={outcome.data['catalog_count']}"
        )
    elif outcome.command == "catalog stats":
        lines.extend(
            (
                f"records: {outcome.data['record_count']}",
                f"tags: {outcome.data['tag_count']}",
                f"relations: {outcome.data['relation_count']}",
            )
        )
    elif outcome.command == "memory query":
        for item in outcome.data["results"]:
            score = "" if item["score"] is None else f" score={item['score']:.6g}"
            lines.append(
                f"{item['memory_id']} [{item['status']}] {item['title']}{score}"
            )
            if item["match_reasons"]:
                lines.append("  reasons: " + ", ".join(item["match_reasons"]))
            if item["warnings"]:
                lines.append("  warnings: " + "; ".join(item["warnings"]))
    elif outcome.command == "memory explain":
        lines.extend(
            (
                f"memory_id: {outcome.data['memory_id']}",
                f"status: {outcome.data['status']}",
                f"revision: {outcome.data['revision']}",
                f"path: {outcome.data['path']}",
                f"scope: {json.dumps(outcome.data['scope'], ensure_ascii=False)}",
                f"validity: {json.dumps(outcome.data['validity'], ensure_ascii=False)}",
                f"confidence: {outcome.data['confidence']}",
                f"catalog_current: {str(outcome.data['catalog_current']).lower()}",
            )
        )
        if outcome.data["warnings"]:
            lines.append("warnings: " + "; ".join(outcome.data["warnings"]))
    elif outcome.command.startswith("memory "):
        lines.extend(
            f"{key}: {value}"
            for key, value in outcome.data.items()
            if key
            in {
                "memory_id",
                "status",
                "revision",
                "path",
                "content_hash",
                "source_hash",
                "canonical",
                "written",
                "catalog_refreshed",
            }
        )
    elif outcome.command == "check":
        for step in outcome.data["steps"]:
            lines.append(f"{'OK' if step['ok'] else 'FAILED'}: {step['name']}")
    elif outcome.command == "diagnose":
        lines.extend(
            (
                f"detected_version: {outcome.data['detected_version']}",
                f"upstream_version: {outcome.data['upstream_version']}",
                f"gaps: {outcome.data['summary']['total']}",
            )
        )
    elif outcome.command == "task archive" and not outcome.data.get(
        "already_archived"
    ):
        plan = outcome.data["plan"]
        lines.extend(
            (
                f"task_id: {plan['task_id']}",
                f"status: {plan['status']}",
                f"archive_id: {plan['archive_id']}",
                f"target: {plan['target']}",
            )
        )
    for diagnostic in outcome.diagnostics:
        lines.append(f"ERROR: {diagnostic.format()}")
    return "\n".join(lines)


def render(outcome: CommandOutcome, output_format: str) -> str:
    return render_json(outcome) if output_format == "json" else render_text(outcome)
