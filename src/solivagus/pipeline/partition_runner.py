"""Translate one cache partition with warm-up / probe / local cache."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from solivagus.cache.local import load_translation, store_translation, translation_cache_key
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import UnitStatus
from solivagus.pipeline.warmup import ProbeDecision, evaluate_probe, run_partition_warmup
from solivagus.providers.openai_compatible import (
    FatalProviderError,
    ProviderError,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from solivagus.providers.prompts import (
    build_stable_prefix,
    build_unit_messages,
    document_user_id,
    extract_unit_translation,
)
from solivagus.providers.usage import UsageRecord
from solivagus.reporting.usage_report import add_usage
from solivagus.util.markdown import (
    make_untranslated_fallback,
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import atomic_write_text, sha256_text


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


def _flat_translate_segment(
    *,
    text: str,
    settings: Settings,
    document_title: str,
    block_id: str,
    glossary: str,
    chat_fn: ChatFn,
    user_id: str | None,
) -> tuple[str, dict[str, Any]]:
    segments = split_passthrough_segments(text)
    output_parts: list[str] = []
    last_usage: dict[str, Any] = {}
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
                raw, finish_reason, usage = chat_fn(
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
                last_usage = usage or {}
                last_error = None
                break
            except FatalProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(2 ** (attempt - 1), 8))
        if last_error is not None:
            raise last_error
    return (
        "\n\n".join(part.strip() for part in output_parts if part.strip()) + "\n",
        last_usage,
    )


def _kv_translate_unit(
    *,
    unit_key: str,
    source_text: str,
    settings: Settings,
    chat_fn: ChatFn,
    stable_system: str,
    stable_user: str,
    warmup_assistant: str,
    user_id: str,
) -> tuple[str, dict[str, Any]]:
    protected, placeholders = protect_markdown(source_text)
    messages = build_unit_messages(
        stable_system=stable_system,
        stable_user=stable_user,
        warmup_assistant=warmup_assistant,
        unit_key=unit_key,
        source_text=protected,
        target_mode=settings.target_mode,  # type: ignore[arg-type]
    )
    if messages[2]["content"] != warmup_assistant:
        raise ProviderError("warm-up assistant content mismatch in unit messages")
    last_error: Exception | None = None
    for attempt in range(1, settings.retries + 1):
        try:
            raw, finish_reason, usage = chat_fn(
                api_base=settings.llm_api_base,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                messages=messages,
                user_id=user_id,
                temperature=settings.temperature,
                send_temperature=settings.send_temperature,
                timeout=settings.timeout_seconds,
                disable_thinking=True,
            )
            if finish_reason and finish_reason != "stop":
                raise ProviderError(f"finish_reason={finish_reason}")
            extracted = extract_unit_translation(raw, unit_key)
            restored = restore_markdown(extracted.strip(), placeholders)
            return restored if restored.endswith("\n") else restored + "\n", usage or {}
        except FatalProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(min(2 ** (attempt - 1), 8))
    assert last_error is not None
    raise last_error


def translate_partition(
    db: Database,
    *,
    document_id: int,
    source_sha256: str,
    document_title: str,
    partition: Any,
    units: list[Any],
    settings: Settings,
    artifact_dir: Path,
    cache_root: Path,
    chat_fn: ChatFn,
    force: bool = False,
    strict: bool = False,
    usage_totals: dict[str, int] | None = None,
) -> dict[str, Any]:
    del document_id  # reserved for future attempt scoping
    units_dir = artifact_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    if usage_totals is None:
        usage_totals = {}

    user_id = str(partition["user_id"] or document_user_id(source_sha256))
    expected = int(partition["expected_cache_tokens"] or partition["source_tokens"] or 0)
    unit_dicts = [
        {"unit_key": u["unit_key"], "source_text": u["source_text"]} for u in units
    ]
    stable_system, stable_user, prefix_hash = build_stable_prefix(
        document_title=document_title,
        target_language=settings.target_language,
        units=unit_dicts,
        prompt_version=settings.prompt_version,
    )

    warmup = run_partition_warmup(
        chat_fn=chat_fn,
        settings=settings,
        stable_system=stable_system,
        stable_user=stable_user,
        prefix_hash=prefix_hash,
        user_id=user_id,
    )
    usage_totals["api_calls"] = usage_totals.get("api_calls", 0) + 1

    decision = ProbeDecision.FULL
    probe_hits = 0
    re_probed = False
    translated = 0
    skipped = 0
    warnings = 0
    assembled: list[dict[str, str]] = []
    first_api_unit_seen = False

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

        cache_key = translation_cache_key(
            source_text=source_text,
            provider="openai-compatible",
            model=settings.llm_model,
            prompt_version=settings.prompt_version,
            target_language=settings.target_language,
            translation_parameters=f"target_mode={settings.target_mode}",
        )

        usage: dict[str, Any] = {}
        from_cache = False
        try:
            cached = None
            if settings.enable_local_translation_cache and not force:
                cached = load_translation(cache_root, cache_key)

            if cached is not None:
                translated_text = str(cached["translation_text"])
                usage_totals["local_cache_hits"] = usage_totals.get("local_cache_hits", 0) + 1
                from_cache = True
            elif decision == ProbeDecision.DEGRADED:
                translated_text, usage = _flat_translate_segment(
                    text=source_text,
                    settings=settings,
                    document_title=document_title,
                    block_id=unit_key,
                    glossary="",
                    chat_fn=chat_fn,
                    user_id=user_id,
                )
                add_usage(usage_totals, usage)
            else:
                translated_text, usage = _kv_translate_unit(
                    unit_key=unit_key,
                    source_text=source_text,
                    settings=settings,
                    chat_fn=chat_fn,
                    stable_system=stable_system,
                    stable_user=stable_user,
                    warmup_assistant=warmup.warmup_assistant,
                    user_id=user_id,
                )
                add_usage(usage_totals, usage)
                if not first_api_unit_seen:
                    first_api_unit_seen = True
                    record = UsageRecord.from_api(usage)
                    probe_hits = record.cache_hit_tokens
                    decision = evaluate_probe(
                        hit_tokens=probe_hits,
                        expected_tokens=expected,
                        min_ratio=settings.cache_probe_min_ratio,
                        warn_ratio=settings.cache_warning_ratio,
                    )
                    if decision == ProbeDecision.DEGRADED:
                        re_probed = True
                        translated_text, usage = _kv_translate_unit(
                            unit_key=unit_key,
                            source_text=source_text,
                            settings=settings,
                            chat_fn=chat_fn,
                            stable_system=stable_system,
                            stable_user=stable_user,
                            warmup_assistant=warmup.warmup_assistant,
                            user_id=user_id,
                        )
                        add_usage(usage_totals, usage)
                        record = UsageRecord.from_api(usage)
                        probe_hits = record.cache_hit_tokens
                        decision = evaluate_probe(
                            hit_tokens=probe_hits,
                            expected_tokens=expected,
                            min_ratio=settings.cache_probe_min_ratio,
                            warn_ratio=settings.cache_warning_ratio,
                        )

            if not from_cache and settings.enable_local_translation_cache:
                store_translation(
                    cache_root,
                    cache_key,
                    {
                        "translation_text": translated_text,
                        "model": settings.llm_model,
                        "prompt_version": settings.prompt_version,
                        "unit_key": unit_key,
                    },
                )

            atomic_write_text(translated_file, translated_text)
            attempt_no = int(unit["attempt_count"] or 0) + 1
            warn_flag = None
            if decision == ProbeDecision.LOW:
                warn_flag = "probe_low"
            elif decision == ProbeDecision.DEGRADED:
                warn_flag = "cache_degraded"
            db.update_unit(
                unit_id,
                status=UnitStatus.DONE.value,
                translation_text=translated_text,
                translation_hash=sha256_text(translated_text),
                provider="openai-compatible",
                model=settings.llm_model,
                attempt_count=attempt_no,
                warning_flags=warn_flag,
            )
            if not from_cache:
                usage_rec = UsageRecord.from_api(usage)
                db.insert_translation_attempt(
                    unit_id,
                    attempt_no,
                    request_hash=cache_key,
                    usage=usage_rec,
                    finish_reason="stop",
                    http_status=usage_rec.http_status,
                )
            translated += 1
            assembled.append(
                {
                    "unit_key": unit_key,
                    "source_text": source_text,
                    "translation_text": translated_text,
                }
            )
        except FatalProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            fallback = make_untranslated_fallback(unit_key, source_text, exc)
            atomic_write_text(translated_file, fallback)
            attempt_no = int(unit["attempt_count"] or 0) + 1
            db.update_unit(
                unit_id,
                status=UnitStatus.FALLBACK.value,
                translation_text=fallback,
                translation_hash=sha256_text(fallback),
                provider="openai-compatible",
                model=settings.llm_model,
                attempt_count=attempt_no,
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
                raise

    part_status = {
        ProbeDecision.FULL: "ready",
        ProbeDecision.LOW: "ready_low_cache",
        ProbeDecision.DEGRADED: "degraded",
    }[decision]
    db.update_partition(
        int(partition["id"]),
        warmup_status="done",
        prefix_hash=prefix_hash,
        user_id=user_id,
        actual_probe_hit_tokens=probe_hits,
        status=part_status,
    )
    db.commit()

    return {
        "translated": translated,
        "skipped": skipped,
        "warnings": warnings,
        "probe_decision": decision.value,
        "probe_hit_tokens": probe_hits,
        "probe_ratio": (probe_hits / expected) if expected else 0.0,
        "assembled": assembled,
        "re_probed": re_probed,
    }
