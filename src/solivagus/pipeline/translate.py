from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    call_chat_api,
)
from solivagus.assembly import assemble_outputs
from solivagus.util.markdown import (
    make_untranslated_fallback,
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import atomic_write_text, sha256_text


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


def _translate_text_segment(
    *,
    text: str,
    settings: Settings,
    document_title: str,
    block_id: str,
    glossary: str,
    chat_fn: ChatFn,
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
            except Exception as exc:  # noqa: BLE001 - retry boundary
                last_error = exc
                time.sleep(min(2 ** (attempt - 1), 8))
        if last_error is not None:
            raise last_error
    return "\n\n".join(part.strip() for part in output_parts if part.strip()) + "\n"


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
    units_dir = artifact_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)

    units = db.list_units(document_id)
    if not units:
        raise ValueError(
            "document has no translation units; import an MVP workspace or run planning first"
        )

    chat = chat_fn or call_chat_api
    document_title = Path(doc["display_name"]).stem
    warnings = 0
    translated_count = 0
    skipped = 0

    db.update_document_status(
        document_id,
        status=DocumentStatus.TRANSLATION_RUNNING.value,
        translation_status="running",
    )

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
        atomic_write_text(source_file, source_text if source_text.endswith("\n") else source_text + "\n")

        try:
            translated = _translate_text_segment(
                text=source_text,
                settings=settings,
                document_title=document_title,
                block_id=unit_key,
                glossary="",
                chat_fn=chat,
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
            db.record_artifact(document_id, name, str(path), sha256_text(path.read_text(encoding="utf-8")))
    db.commit()
    return {
        "document_id": document_id,
        "translated": translated_count,
        "skipped": skipped,
        "warnings": warnings,
        "artifact_dir": str(artifact_dir),
        "status": final_status,
    }
