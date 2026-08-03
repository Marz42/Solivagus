from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from solivagus.assembly import assemble_outputs
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.partition_runner import translate_partition
from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    call_chat_api,
)
from solivagus.providers.prompts import document_user_id
from solivagus.reporting.usage_report import empty_usage_totals, write_usage_report
from solivagus.util.markdown import (
    make_untranslated_fallback,
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import atomic_write_text, sha256_text
from solivagus.workspace import translation_cache_root


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


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
    db.update_document_status(
        document_id,
        status=DocumentStatus.TRANSLATION_RUNNING.value,
        translation_status="running",
    )

    partitions = db.list_partitions(document_id)
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

    units_by_partition: dict[int | None, list[Any]] = {}
    for unit in units:
        pid = unit["partition_id"]
        units_by_partition.setdefault(int(pid) if pid is not None else None, []).append(unit)

    try:
        for partition in partitions:
            part_id = int(partition["id"])
            part_units = units_by_partition.get(part_id, [])
            if not part_units:
                continue
            result = translate_partition(
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
        "cache_hit_tokens": usage_totals.get("cache_hit_tokens", 0),
        "local_cache_hits": usage_totals.get("local_cache_hits", 0),
        "partitions": probe_summaries,
    }
