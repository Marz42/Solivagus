from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable

from solivagus.assembly import assemble_outputs
from solivagus.concurrency.limits import ConcurrencyGate, Gate
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.partition_runner import translate_partition_async
from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    call_chat_api,
)
from solivagus.providers.prompts import document_user_id
from solivagus.reporting.usage_report import empty_usage_totals, write_usage_report
from solivagus.style.capsule import StyleCapsule, build_next_capsule, empty_capsule
from solivagus.util.markdown import (
    make_untranslated_fallback,
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import atomic_write_json, atomic_write_text, sha256_text
from solivagus.workspace import translation_cache_root


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


def _persist_partition_capsule(
    db: Database,
    *,
    document_id: int,
    part_id: int,
    capsule: StyleCapsule,
    capsule_dir: Path,
) -> StyleCapsule:
    fields = capsule.to_db_fields()
    db.insert_style_capsule(
        document_id,
        version=int(fields["version"]),
        rules_json=str(fields["rules_json"]),
        terminology_json=str(fields["terminology_json"]),
        examples_json=str(fields["examples_json"]),
        boundary_context_json=str(fields["boundary_context_json"]),
        content_hash=str(fields["content_hash"]),
        source_partition_id=part_id,
    )
    capsule_path = capsule_dir / f"v{capsule.version}.json"
    atomic_write_json(
        capsule_path,
        {
            "version": capsule.version,
            "style_rules": capsule.style_rules,
            "terminology": capsule.terminology,
            "examples": capsule.examples,
            "boundary_context": capsule.boundary_context,
            "content_hash": capsule.content_hash(),
            "source_partition_id": part_id,
        },
    )
    db.record_artifact(
        document_id,
        "style_capsule",
        str(capsule_path),
        capsule.content_hash(),
    )
    db.commit()
    return capsule


def reconcile_missing_style_capsules(
    db: Database,
    *,
    document_id: int,
    partitions: list[Any],
    units_by_partition: dict[int | None, list[Any]],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Rebuild missing per-partition capsules from DONE units without provider calls.

    Walks partitions in order from empty_capsule(). Existing rows for a partition
    are reused; gaps are filled via build_next_capsule from that partition's
    completed translations (deterministic recovery after replan/clear).
    """
    capsule_dir = artifact_dir / "style_capsules"
    capsule_dir.mkdir(parents=True, exist_ok=True)
    capsule = empty_capsule()
    rebuilt: list[int] = []
    reused: list[int] = []

    for partition in partitions:
        part_id = int(partition["id"])
        part_units = units_by_partition.get(part_id, [])
        assembled = [
            {
                "unit_key": str(u["unit_key"]),
                "source_text": str(u["source_text"] or ""),
                "translation_text": str(u["translation_text"] or ""),
            }
            for u in part_units
            if str(u["status"]) == UnitStatus.DONE.value and u["translation_text"]
        ]
        stored = db.get_style_capsule_for_partition(document_id, part_id)
        if stored is not None:
            capsule = StyleCapsule.from_db_row(stored)
            reused.append(part_id)
            continue
        if not assembled:
            continue
        next_capsule = build_next_capsule(capsule, assembled)
        _persist_partition_capsule(
            db,
            document_id=document_id,
            part_id=part_id,
            capsule=next_capsule,
            capsule_dir=capsule_dir,
        )
        capsule = next_capsule
        rebuilt.append(part_id)

    latest = db.get_latest_style_capsule(document_id)
    return {
        "rebuilt_partition_ids": rebuilt,
        "reused_partition_ids": reused,
        "latest_version": int(latest["version"]) if latest is not None else 0,
        "latest_terminology": (
            StyleCapsule.from_db_row(latest).terminology if latest is not None else {}
        ),
    }


async def _translate_all_partitions_async(
    db: Database,
    *,
    document_id: int,
    doc: Any,
    partitions: list[Any],
    units_by_partition: dict[int | None, list[Any]],
    settings: Settings,
    artifact_dir: Path,
    cache_root: Path,
    chat: ChatFn,
    force: bool,
    strict: bool,
    usage_totals: dict[str, int],
    document_title: str,
    capsule: StyleCapsule,
    capsule_dir: Path,
    shared_global_gate: Gate | None,
) -> tuple[int, int, int, list[dict[str, str]], list[dict[str, Any]]]:
    """Run every partition on one event loop so asyncio gates stay valid."""
    global_gate: Gate = shared_global_gate or ConcurrencyGate(
        settings.global_concurrency, maximum=settings.max_global_concurrency
    )
    document_gate = ConcurrencyGate(
        settings.per_document_concurrency, maximum=settings.max_global_concurrency
    )
    translated_count = 0
    skipped = 0
    warnings = 0
    assembled: list[dict[str, str]] = []
    probe_summaries: list[dict[str, Any]] = []

    for partition in partitions:
        part_id = int(partition["id"])
        part_units = units_by_partition.get(part_id, [])
        if not part_units:
            continue
        result = await translate_partition_async(
            db,
            document_id=document_id,
            source_sha256=str(doc["source_sha256"]),
            document_title=document_title,
            partition=partition,
            units=part_units,
            settings=settings,
            artifact_dir=artifact_dir,
            cache_root=cache_root,
            chat_fn=chat,
            force=force,
            strict=strict,
            usage_totals=usage_totals,
            global_gate=global_gate,
            document_gate=document_gate,
            style_capsule=capsule,
        )
        translated_count += int(result["translated"])
        skipped += int(result["skipped"])
        warnings += int(result["warnings"])
        assembled.extend(result["assembled"])
        probe_summaries.append(
            {
                "partition_id": part_id,
                "sequence_index": partition["sequence_index"],
                "probe_decision": result["probe_decision"],
                "probe_hit_tokens": result["probe_hit_tokens"],
                "probe_ratio": result["probe_ratio"],
                "re_probed": result["re_probed"],
                "partition_concurrency": result.get("partition_concurrency"),
                "style_capsule_version": result.get("style_capsule_version"),
                "rewarmed": result.get("rewarmed"),
            }
        )
        # Freeze next capsule at partition boundary for subsequent partitions.
        entry_capsule = result.get("style_capsule") or capsule
        if result.get("skipped_all"):
            stored = db.get_style_capsule_for_partition(document_id, part_id)
            if stored is not None:
                capsule = StyleCapsule.from_db_row(stored)
                continue
            # Crash window: units done but capsule never persisted — rebuild + write.
            next_capsule = build_next_capsule(entry_capsule, result["assembled"])
        else:
            next_capsule = build_next_capsule(entry_capsule, result["assembled"])
        _persist_partition_capsule(
            db,
            document_id=document_id,
            part_id=part_id,
            capsule=next_capsule,
            capsule_dir=capsule_dir,
        )
        capsule = next_capsule

    return translated_count, skipped, warnings, assembled, probe_summaries


def _run_partitions(
    db: Database,
    *,
    document_id: int,
    doc: Any,
    units: list[Any],
    partitions: list[Any],
    units_by_partition: dict[int | None, list[Any]],
    settings: Settings,
    artifact_dir: Path,
    cache_root: Path,
    chat: ChatFn,
    force: bool,
    strict: bool,
    usage_totals: dict[str, int],
    document_title: str,
    capsule: StyleCapsule,
    capsule_dir: Path,
    shared_global_gate: Gate | None,
) -> tuple[int, int, int, list[dict[str, str]], list[dict[str, Any]]]:
    del units  # ordering restored by caller via sequence_index
    return asyncio.run(
        _translate_all_partitions_async(
            db,
            document_id=document_id,
            doc=doc,
            partitions=partitions,
            units_by_partition=units_by_partition,
            settings=settings,
            artifact_dir=artifact_dir,
            cache_root=cache_root,
            chat=chat,
            force=force,
            strict=strict,
            usage_totals=usage_totals,
            document_title=document_title,
            capsule=capsule,
            capsule_dir=capsule_dir,
            shared_global_gate=shared_global_gate,
        )
    )


def _legacy_translate_text_segment(
    *,
    text: str,
    settings: Settings,
    document_title: str,
    block_id: str,
    glossary: str,
    chat_fn: ChatFn,
    user_id: str | None = None,
) -> str:
    segments = split_passthrough_segments(text)
    output_parts: list[str] = []
    for kind, value in segments:
        if kind != "text":
            output_parts.append(value)
            continue
        protected, placeholders = protect_markdown(value)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            target_language=settings.target_language,
            document_title=document_title,
            block_id=block_id,
            glossary=glossary or "(空)",
            protected_markdown=protected,
        )
        last_error: Exception | None = None
        for attempt in range(1, settings.retries + 1):
            try:
                raw, finish_reason, _usage = chat_fn(
                    api_base=settings.llm_api_base,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    user_id=user_id,
                    temperature=settings.temperature,
                    send_temperature=settings.send_temperature,
                    timeout=settings.timeout_seconds,
                    disable_thinking=True,
                )
                if finish_reason and finish_reason != "stop":
                    raise ProviderError(f"finish_reason={finish_reason}")
                restored = restore_markdown(raw.strip(), placeholders)
                output_parts.append(restored)
                last_error = None
                break
            except FatalProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(2 ** (attempt - 1), 8))
        if last_error is not None:
            raise last_error
    return "\n\n".join(part.strip() for part in output_parts if part.strip()) + "\n"


def _translate_without_partitions(
    db: Database,
    *,
    document_id: int,
    doc: Any,
    settings: Settings,
    force: bool,
    strict: bool,
    chat: ChatFn,
) -> dict[str, Any]:
    artifact_dir = Path(doc["artifact_dir"])
    units_dir = artifact_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    units = db.list_units(document_id)
    document_title = Path(doc["display_name"]).stem
    user_id = document_user_id(str(doc["source_sha256"]))
    warnings = 0
    translated_count = 0
    skipped = 0
    assembled: list[dict[str, str]] = []

    for unit in units:
        unit_id = int(unit["id"])
        unit_key = str(unit["unit_key"])
        source_text = str(unit["source_text"])
        status = str(unit["status"])
        if status == UnitStatus.DONE.value and unit["translation_text"] and not force:
            skipped += 1
            assembled.append(
                {
                    "unit_key": unit_key,
                    "source_text": source_text,
                    "translation_text": str(unit["translation_text"]),
                }
            )
            continue
        source_file = units_dir / f"{unit_key}.source.md"
        translated_file = units_dir / f"{unit_key}.zh.md"
        atomic_write_text(
            source_file, source_text if source_text.endswith("\n") else source_text + "\n"
        )
        try:
            translated = _legacy_translate_text_segment(
                text=source_text,
                settings=settings,
                document_title=document_title,
                block_id=unit_key,
                glossary="",
                chat_fn=chat,
                user_id=user_id,
            )
            atomic_write_text(translated_file, translated)
            db.update_unit(
                unit_id,
                status=UnitStatus.DONE.value,
                translation_text=translated,
                translation_hash=sha256_text(translated),
                provider="openai-compatible",
                model=settings.llm_model,
                attempt_count=int(unit["attempt_count"] or 0) + 1,
            )
            translated_count += 1
            assembled.append(
                {
                    "unit_key": unit_key,
                    "source_text": source_text,
                    "translation_text": translated,
                }
            )
        except FatalProviderError:
            db.update_document_status(
                document_id,
                status=DocumentStatus.FAILED.value,
                translation_status="failed",
            )
            db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            fallback = make_untranslated_fallback(unit_key, source_text, exc)
            atomic_write_text(translated_file, fallback)
            db.update_unit(
                unit_id,
                status=UnitStatus.FALLBACK.value,
                translation_text=fallback,
                translation_hash=sha256_text(fallback),
                provider="openai-compatible",
                model=settings.llm_model,
                attempt_count=int(unit["attempt_count"] or 0) + 1,
                warning_flags="fallback",
            )
            warnings += 1
            assembled.append(
                {
                    "unit_key": unit_key,
                    "source_text": source_text,
                    "translation_text": fallback,
                }
            )
            if strict:
                db.update_document_status(
                    document_id,
                    status=DocumentStatus.FAILED.value,
                    translation_status="failed",
                )
                db.commit()
                raise

    assemble_outputs(
        artifact_dir,
        assembled,
        document_title=document_title,
        pdf_name=str(doc["display_name"]),
        model=settings.llm_model,
        make_bilingual=True,
    )
    final_status = (
        DocumentStatus.TRANSLATION_COMPLETE_WITH_WARNINGS.value
        if warnings
        else DocumentStatus.TRANSLATION_COMPLETE.value
    )
    db.update_document_status(
        document_id,
        status=final_status,
        translation_status="complete_with_warnings" if warnings else "complete",
    )
    for name in ("translated.zh.md", "translated.bilingual.md"):
        path = artifact_dir / name
        if path.is_file():
            db.record_artifact(
                document_id, name, str(path), sha256_text(path.read_text(encoding="utf-8"))
            )
    db.commit()
    return {
        "document_id": document_id,
        "translated": translated_count,
        "skipped": skipped,
        "warnings": warnings,
        "artifact_dir": str(artifact_dir),
        "status": final_status,
        "mode": "legacy_flat",
    }


def run_translate_stage(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    force: bool = False,
    strict: bool = False,
    chat_fn: ChatFn | None = None,
    global_gate: Gate | None = None,
) -> dict[str, Any]:
    doc = db.fetchone("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise ValueError(f"document not found: {document_id}")

    artifact_dir = Path(doc["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    units = db.list_units(document_id)
    if not units:
        raise ValueError(
            "document has no translation units; import an MVP workspace or run planning first"
        )

    chat = chat_fn or call_chat_api
    partitions = db.list_partitions(document_id)

    def _all_units_done() -> bool:
        return (not force) and all(
            str(u["status"]) == UnitStatus.DONE.value and bool(u["translation_text"])
            for u in units
        )

    # Fully translated document: reconcile capsules then assemble — never call provider.
    if partitions and _all_units_done():
        document_title = Path(doc["display_name"]).stem
        units_by_partition: dict[int | None, list[Any]] = {}
        for unit in units:
            pid = unit["partition_id"]
            units_by_partition.setdefault(int(pid) if pid is not None else None, []).append(
                unit
            )
        capsule_reconcile = reconcile_missing_style_capsules(
            db,
            document_id=document_id,
            partitions=partitions,
            units_by_partition=units_by_partition,
            artifact_dir=artifact_dir,
        )
        assembled = [
            {
                "unit_key": str(u["unit_key"]),
                "source_text": str(u["source_text"]),
                "translation_text": str(u["translation_text"]),
            }
            for u in units
        ]
        assemble_outputs(
            artifact_dir,
            assembled,
            document_title=document_title,
            pdf_name=str(doc["display_name"]),
            model=settings.llm_model,
            make_bilingual=True,
        )
        final_status = DocumentStatus.TRANSLATION_COMPLETE.value
        # Preserve warnings status if already marked with warnings.
        current = str(doc["status"] or "")
        if current.endswith("warnings") or current == DocumentStatus.TRANSLATION_COMPLETE_WITH_WARNINGS.value:
            final_status = DocumentStatus.TRANSLATION_COMPLETE_WITH_WARNINGS.value
        db.update_document_status(
            document_id,
            status=final_status,
            translation_status="complete_with_warnings"
            if final_status.endswith("warnings")
            else "complete",
        )
        for name in ("translated.zh.md", "translated.bilingual.md"):
            path = artifact_dir / name
            if path.is_file():
                db.record_artifact(
                    document_id, name, str(path), sha256_text(path.read_text(encoding="utf-8"))
                )
        from solivagus.pipeline.manifest import write_document_manifest

        manifest_path = write_document_manifest(
            artifact_dir,
            document_id=document_id,
            display_name=str(doc["display_name"]),
            source_sha256=str(doc["source_sha256"]),
            status=final_status,
            model=settings.llm_model,
            extra={"translated": 0, "warnings": 0, "skipped": len(units)},
        )
        db.record_artifact(
            document_id,
            "manifest",
            str(manifest_path),
            sha256_text(manifest_path.read_text(encoding="utf-8")),
        )
        db.commit()
        return {
            "document_id": document_id,
            "translated": 0,
            "skipped": len(units),
            "warnings": 0,
            "artifact_dir": str(artifact_dir),
            "status": final_status,
            "mode": "partition_cache",
            "manifest": str(manifest_path),
            "skipped_all": True,
            "capsule_reconcile": capsule_reconcile,
            "partitions": [],
        }

    db.update_document_status(
        document_id,
        status=DocumentStatus.TRANSLATION_RUNNING.value,
        translation_status="running",
    )

    if not partitions:
        return _translate_without_partitions(
            db,
            document_id=document_id,
            doc=doc,
            settings=settings,
            force=force,
            strict=strict,
            chat=chat,
        )

    document_title = Path(doc["display_name"]).stem
    cache_root = translation_cache_root(settings.workspace)
    cache_root.mkdir(parents=True, exist_ok=True)
    usage_totals = empty_usage_totals()
    assembled: list[dict[str, str]] = []
    translated_count = 0
    skipped = 0
    warnings = 0
    probe_summaries: list[dict[str, Any]] = []
    # Always enter partition 1 with an empty capsule. Prior generations are cleared
    # on replan; mid-doc resume rebuilds from stored/partition-skip recovery.
    capsule: StyleCapsule = empty_capsule()
    capsule_dir = artifact_dir / "style_capsules"
    capsule_dir.mkdir(parents=True, exist_ok=True)

    units_by_partition: dict[int | None, list[Any]] = {}
    for unit in units:
        pid = unit["partition_id"]
        units_by_partition.setdefault(int(pid) if pid is not None else None, []).append(unit)

    try:
        translated_count, skipped, warnings, assembled, probe_summaries = _run_partitions(
            db,
            document_id=document_id,
            doc=doc,
            units=units,
            partitions=partitions,
            units_by_partition=units_by_partition,
            settings=settings,
            artifact_dir=artifact_dir,
            cache_root=cache_root,
            chat=chat,
            force=force,
            strict=strict,
            usage_totals=usage_totals,
            document_title=document_title,
            capsule=capsule,
            capsule_dir=capsule_dir,
            shared_global_gate=global_gate,
        )
    except FatalProviderError:
        db.update_document_status(
            document_id,
            status=DocumentStatus.FAILED.value,
            translation_status="failed",
        )
        db.commit()
        raise

    # Preserve sequence_index order across partitions.
    assembled.sort(
        key=lambda item: next(
            (int(u["sequence_index"]) for u in units if u["unit_key"] == item["unit_key"]),
            0,
        )
    )

    assemble_outputs(
        artifact_dir,
        assembled,
        document_title=document_title,
        pdf_name=str(doc["display_name"]),
        model=settings.llm_model,
        make_bilingual=True,
    )
    report = {
        "document_id": document_id,
        "model": settings.llm_model,
        "prompt_version": settings.prompt_version,
        "target_mode": settings.target_mode,
        "totals": usage_totals,
        "partitions": probe_summaries,
    }
    report_path = write_usage_report(artifact_dir, report)
    db.record_artifact(
        document_id,
        "usage_report",
        str(report_path),
        sha256_text(report_path.read_text(encoding="utf-8")),
    )

    final_status = (
        DocumentStatus.TRANSLATION_COMPLETE_WITH_WARNINGS.value
        if warnings or any(p["probe_decision"] != "full" for p in probe_summaries)
        else DocumentStatus.TRANSLATION_COMPLETE.value
    )
    db.update_document_status(
        document_id,
        status=final_status,
        translation_status="complete_with_warnings"
        if final_status.endswith("warnings")
        else "complete",
    )
    for name in ("translated.zh.md", "translated.bilingual.md"):
        path = artifact_dir / name
        if path.is_file():
            db.record_artifact(
                document_id, name, str(path), sha256_text(path.read_text(encoding="utf-8"))
            )

    from solivagus.pipeline.manifest import write_document_manifest

    manifest_path = write_document_manifest(
        artifact_dir,
        document_id=document_id,
        display_name=str(doc["display_name"]),
        source_sha256=str(doc["source_sha256"]),
        status=final_status,
        model=settings.llm_model,
        extra={"translated": translated_count, "warnings": warnings},
    )
    db.record_artifact(
        document_id,
        "manifest",
        str(manifest_path),
        sha256_text(manifest_path.read_text(encoding="utf-8")),
    )
    db.commit()
    return {
        "document_id": document_id,
        "translated": translated_count,
        "skipped": skipped,
        "warnings": warnings,
        "artifact_dir": str(artifact_dir),
        "status": final_status,
        "mode": "partition_cache",
        "usage_report": str(report_path),
        "manifest": str(manifest_path),
        "cache_hit_tokens": usage_totals.get("cache_hit_tokens", 0),
        "local_cache_hits": usage_totals.get("local_cache_hits", 0),
        "partitions": probe_summaries,
    }
