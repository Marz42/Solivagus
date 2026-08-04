"""Translate one cache partition with warm-up / probe / local cache / async units."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from solivagus.cache.local import load_translation, store_translation, translation_cache_key
from solivagus.concurrency.limits import (
    ConcurrencyConfig,
    ConcurrencyGate,
    NestedGates,
    partition_limit_for_probe,
)
from solivagus.concurrency.writer import DbWriter
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import UnitStatus
from solivagus.pipeline.bisect import bisect_source_text
from solivagus.pipeline.warmup import ProbeDecision, evaluate_probe, run_partition_warmup
from solivagus.providers.async_openai import is_rate_limited_error
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
from solivagus.style.capsule import StyleCapsule, empty_capsule, provisional_from_seed, select_seed_unit
from solivagus.util.markdown import (
    make_untranslated_fallback,
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import atomic_write_text, sha256_text


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


async def _invoke_chat(chat_fn: ChatFn, **kwargs: Any) -> tuple[str, str | None, dict[str, Any]]:
    if asyncio.iscoroutinefunction(chat_fn):
        return await chat_fn(**kwargs)  # type: ignore[misc]
    return await asyncio.to_thread(lambda: chat_fn(**kwargs))


def _concurrency_config(settings: Settings) -> ConcurrencyConfig:
    return ConcurrencyConfig(
        global_limit=settings.global_concurrency,
        per_document_limit=settings.per_document_concurrency,
        per_partition_limit=settings.per_partition_concurrency,
        max_global_limit=settings.max_global_concurrency,
        low_probe_limit=settings.low_probe_concurrency,
        adaptive=settings.adaptive_concurrency,
    )


async def _flat_translate_segment_async(
    *,
    text: str,
    settings: Settings,
    document_title: str,
    block_id: str,
    glossary: str,
    chat_fn: ChatFn,
    user_id: str | None,
    partition_gate: ConcurrencyGate | None = None,
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
                raw, finish_reason, usage = await _invoke_chat(
                    chat_fn,
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
                if partition_gate is not None:
                    await partition_gate.record_success(adaptive=settings.adaptive_concurrency)
                last_error = None
                break
            except FatalProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if partition_gate is not None and is_rate_limited_error(exc):
                    await partition_gate.record_rate_limit(adaptive=settings.adaptive_concurrency)
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        if last_error is not None:
            raise last_error
    return (
        "\n\n".join(part.strip() for part in output_parts if part.strip()) + "\n",
        last_usage,
    )


async def _kv_translate_unit_async(
    *,
    unit_key: str,
    source_text: str,
    settings: Settings,
    chat_fn: ChatFn,
    stable_system: str,
    stable_user: str,
    warmup_assistant: str,
    user_id: str,
    partition_gate: ConcurrencyGate | None = None,
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
            raw, finish_reason, usage = await _invoke_chat(
                chat_fn,
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
            if partition_gate is not None:
                await partition_gate.record_success(adaptive=settings.adaptive_concurrency)
            return restored if restored.endswith("\n") else restored + "\n", usage or {}
        except FatalProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if partition_gate is not None and is_rate_limited_error(exc):
                await partition_gate.record_rate_limit(adaptive=settings.adaptive_concurrency)
            await asyncio.sleep(min(2 ** (attempt - 1), 8))
    assert last_error is not None
    raise last_error


def _flat_translate_segment(**kwargs: Any) -> tuple[str, dict[str, Any]]:
    return asyncio.run(_flat_translate_segment_async(**kwargs))


def _kv_translate_unit(**kwargs: Any) -> tuple[str, dict[str, Any]]:
    return asyncio.run(_kv_translate_unit_async(**kwargs))


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
    global_gate: ConcurrencyGate | None = None,
    document_gate: ConcurrencyGate | None = None,
    style_capsule: StyleCapsule | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        translate_partition_async(
            db,
            document_id=document_id,
            source_sha256=source_sha256,
            document_title=document_title,
            partition=partition,
            units=units,
            settings=settings,
            artifact_dir=artifact_dir,
            cache_root=cache_root,
            chat_fn=chat_fn,
            force=force,
            strict=strict,
            usage_totals=usage_totals,
            global_gate=global_gate,
            document_gate=document_gate,
            style_capsule=style_capsule,
        )
    )


async def translate_partition_async(
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
    global_gate: ConcurrencyGate | None = None,
    document_gate: ConcurrencyGate | None = None,
    style_capsule: StyleCapsule | None = None,
) -> dict[str, Any]:
    del document_id
    units_dir = artifact_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    if usage_totals is None:
        usage_totals = {}

    cfg = _concurrency_config(settings)
    global_gate = global_gate or ConcurrencyGate(cfg.global_limit)
    document_gate = document_gate or ConcurrencyGate(cfg.per_document_limit)
    writer = DbWriter()

    capsule = style_capsule or empty_capsule()
    # Partition-1 bootstrap: translate a representative seed unit first.
    if capsule.version == 0 and not capsule.provisional and units:
        seed = select_seed_unit(units)
        if seed is not None:
            seed_key = str(seed["unit_key"])
            units = [seed] + [u for u in units if str(u["unit_key"]) != seed_key]

    user_id = str(partition["user_id"] or document_user_id(source_sha256))
    expected = int(partition["expected_cache_tokens"] or partition["source_tokens"] or 0)
    unit_dicts = [
        {"unit_key": u["unit_key"], "source_text": u["source_text"]} for u in units
    ]

    def _rebuild_prefix() -> tuple[str, str, str]:
        return build_stable_prefix(
            document_title=document_title,
            target_language=settings.target_language,
            units=unit_dicts,
            style_capsule=capsule.to_prompt_text(),
            prompt_version=settings.prompt_version,
        )

    stable_system, stable_user, prefix_hash = _rebuild_prefix()

    warmup = await asyncio.to_thread(
        run_partition_warmup,
        chat_fn=chat_fn,
        settings=settings,
        stable_system=stable_system,
        stable_user=stable_user,
        prefix_hash=prefix_hash,
        user_id=user_id,
    )
    usage_totals["api_calls"] = usage_totals.get("api_calls", 0) + 1
    rewarmed = False

    decision = ProbeDecision.FULL
    probe_hits = 0
    re_probed = False
    translated = 0
    skipped = 0
    warnings = 0
    assembled: list[dict[str, str]] = []
    pending_after_probe: list[Any] = []
    barrier_done = False
    partition_gate = ConcurrencyGate(1)

    async def persist_success(
        *,
        unit: Any,
        translated_text: str,
        usage: dict[str, Any],
        from_cache: bool,
        cache_key: str,
        warn_flag: str | None,
    ) -> None:
        nonlocal translated
        unit_id = int(unit["id"])
        unit_key = str(unit["unit_key"])
        source_text = str(unit["source_text"])
        translated_file = units_dir / f"{unit_key}.zh.md"
        atomic_write_text(translated_file, translated_text)
        attempt_no = int(unit["attempt_count"] or 0) + 1

        def _write() -> None:
            db.update_unit(
                unit_id,
                status=UnitStatus.DONE.value,
                translation_text=translated_text,
                translation_hash=sha256_text(translated_text),
                provider="openai-compatible",
                model=settings.llm_model,
                attempt_count=attempt_no,
                warning_flags=warn_flag,
                prompt_version=settings.prompt_version,
                style_capsule_version=capsule.version_label(),
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
            db.commit()

        await writer.run(_write)
        translated += 1
        assembled.append(
            {
                "unit_key": unit_key,
                "source_text": source_text,
                "translation_text": translated_text,
            }
        )

    async def persist_fallback(unit: Any, exc: Exception) -> None:
        nonlocal warnings
        unit_id = int(unit["id"])
        unit_key = str(unit["unit_key"])
        source_text = str(unit["source_text"])
        fallback = make_untranslated_fallback(unit_key, source_text, exc)
        translated_file = units_dir / f"{unit_key}.zh.md"
        atomic_write_text(translated_file, fallback)
        attempt_no = int(unit["attempt_count"] or 0) + 1

        def _write() -> None:
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
            db.commit()

        await writer.run(_write)
        warnings += 1
        assembled.append(
            {
                "unit_key": unit_key,
                "source_text": source_text,
                "translation_text": fallback,
            }
        )

    async def process_one_unit(
        unit: Any,
        *,
        under_gates: bool,
        is_probe: bool = False,
    ) -> None:
        nonlocal decision, probe_hits, re_probed, barrier_done, partition_gate
        nonlocal capsule, stable_system, stable_user, prefix_hash, warmup, rewarmed
        unit_key = str(unit["unit_key"])
        source_text = str(unit["source_text"])
        source_file = units_dir / f"{unit_key}.source.md"
        atomic_write_text(
            source_file, source_text if source_text.endswith("\n") else source_text + "\n"
        )
        cache_key = translation_cache_key(
            source_text=source_text,
            provider="openai-compatible",
            model=settings.llm_model,
            prompt_version=settings.prompt_version,
            target_language=settings.target_language,
            style_capsule_hash=capsule.content_hash(),
            translation_parameters=f"target_mode={settings.target_mode}",
        )

        async def _do_translate() -> tuple[str, dict[str, Any], bool]:
            nonlocal decision, probe_hits, re_probed, partition_gate, barrier_done
            nonlocal capsule, stable_system, stable_user, prefix_hash, warmup, rewarmed
            cached = None
            if settings.enable_local_translation_cache and not force:
                cached = load_translation(cache_root, cache_key)
            if cached is not None:
                usage_totals["local_cache_hits"] = usage_totals.get("local_cache_hits", 0) + 1
                if is_probe:
                    limit = partition_limit_for_probe(decision.value, cfg)
                    partition_gate = ConcurrencyGate(limit)
                    barrier_done = True
                return str(cached["translation_text"]), {}, True

            if decision == ProbeDecision.DEGRADED:
                text, usage = await _flat_translate_segment_async(
                    text=source_text,
                    settings=settings,
                    document_title=document_title,
                    block_id=unit_key,
                    glossary="",
                    chat_fn=chat_fn,
                    user_id=user_id,
                    partition_gate=partition_gate,
                )
                add_usage(usage_totals, usage)
                if is_probe:
                    barrier_done = True
                return text, usage, False

            text, usage = await _kv_translate_unit_async(
                unit_key=unit_key,
                source_text=source_text,
                settings=settings,
                chat_fn=chat_fn,
                stable_system=stable_system,
                stable_user=stable_user,
                warmup_assistant=warmup.warmup_assistant,
                user_id=user_id,
                partition_gate=partition_gate,
            )
            add_usage(usage_totals, usage)
            if is_probe:
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
                    text, usage = await _kv_translate_unit_async(
                        unit_key=unit_key,
                        source_text=source_text,
                        settings=settings,
                        chat_fn=chat_fn,
                        stable_system=stable_system,
                        stable_user=stable_user,
                        warmup_assistant=warmup.warmup_assistant,
                        user_id=user_id,
                        partition_gate=partition_gate,
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
                # Phase 6: provisional capsule from seed, then rebuild prefix + re-warmup.
                if capsule.version == 0 and not capsule.provisional:
                    capsule = provisional_from_seed(
                        capsule,
                        source_text=source_text,
                        translation_text=text,
                    )
                    stable_system, stable_user, prefix_hash = _rebuild_prefix()
                    warmup = await asyncio.to_thread(
                        run_partition_warmup,
                        chat_fn=chat_fn,
                        settings=settings,
                        stable_system=stable_system,
                        stable_user=stable_user,
                        prefix_hash=prefix_hash,
                        user_id=user_id,
                    )
                    usage_totals["api_calls"] = usage_totals.get("api_calls", 0) + 1
                    rewarmed = True
                # Warm-up barrier: open concurrency for remaining units.
                limit = partition_limit_for_probe(decision.value, cfg)
                partition_gate = ConcurrencyGate(limit)
                barrier_done = True
            return text, usage, False

        try:
            if under_gates:
                async with NestedGates(global_gate, document_gate, partition_gate):
                    translated_text, usage, from_cache = await _do_translate()
            else:
                translated_text, usage, from_cache = await _do_translate()

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
            warn_flag = None
            if decision == ProbeDecision.LOW:
                warn_flag = "probe_low"
            elif decision == ProbeDecision.DEGRADED:
                warn_flag = "cache_degraded"
            await persist_success(
                unit=unit,
                translated_text=translated_text,
                usage=usage,
                from_cache=from_cache,
                cache_key=cache_key,
                warn_flag=warn_flag,
            )
        except FatalProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Brief §19.2: structural / persistent failure → bisect before English fallback.
            halves = bisect_source_text(source_text)
            max_depth = max(0, int(settings.unit_bisect_max_depth))
            if halves and max_depth > 0 and not is_probe:
                left_src, right_src = halves
                try:
                    left_text, left_usage = await _kv_translate_unit_async(
                        unit_key=f"{unit_key}:a",
                        source_text=left_src,
                        settings=settings,
                        chat_fn=chat_fn,
                        stable_system=stable_system,
                        stable_user=stable_user,
                        warmup_assistant=warmup.warmup_assistant,
                        user_id=user_id,
                        partition_gate=partition_gate if under_gates else None,
                    )
                    right_text, right_usage = await _kv_translate_unit_async(
                        unit_key=f"{unit_key}:b",
                        source_text=right_src,
                        settings=settings,
                        chat_fn=chat_fn,
                        stable_system=stable_system,
                        stable_user=stable_user,
                        warmup_assistant=warmup.warmup_assistant,
                        user_id=user_id,
                        partition_gate=partition_gate if under_gates else None,
                    )
                    combined = (left_text.rstrip() + "\n\n" + right_text.lstrip()).rstrip() + "\n"
                    merged_usage = dict(left_usage or {})
                    for key in (
                        "prompt_tokens",
                        "completion_tokens",
                        "prompt_cache_hit_tokens",
                        "prompt_cache_miss_tokens",
                        "cache_hit_tokens",
                        "cache_miss_tokens",
                    ):
                        if key in (right_usage or {}):
                            merged_usage[key] = int(merged_usage.get(key) or 0) + int(
                                right_usage.get(key) or 0
                            )
                    await persist_success(
                        unit=unit,
                        translated_text=combined,
                        usage=merged_usage,
                        from_cache=False,
                        cache_key=cache_key,
                        warn_flag="bisected",
                    )
                    return
                except FatalProviderError:
                    raise
                except Exception:
                    pass
            await persist_fallback(unit, exc)
            if strict:
                raise

    # Pass 1: skip done units; run first API unit as probe (serial barrier).
    for unit in units:
        status = str(unit["status"])
        if status == UnitStatus.DONE.value and unit["translation_text"] and not force:
            skipped += 1
            assembled.append(
                {
                    "unit_key": str(unit["unit_key"]),
                    "source_text": str(unit["source_text"]),
                    "translation_text": str(unit["translation_text"]),
                }
            )
            continue
        if not barrier_done:
            await process_one_unit(unit, under_gates=False, is_probe=True)
        else:
            pending_after_probe.append(unit)

    # Pass 2: concurrent remainder after warm-up/probe barrier.
    if pending_after_probe:
        await asyncio.gather(
            *[
                process_one_unit(unit, under_gates=True, is_probe=False)
                for unit in pending_after_probe
            ]
        )

    part_status = {
        ProbeDecision.FULL: "ready",
        ProbeDecision.LOW: "ready_low_cache",
        ProbeDecision.DEGRADED: "degraded",
    }[decision]

    def _update_partition() -> None:
        db.update_partition(
            int(partition["id"]),
            warmup_status="done",
            prefix_hash=prefix_hash,
            user_id=user_id,
            actual_probe_hit_tokens=probe_hits,
            status=part_status,
        )
        db.commit()

    await writer.run(_update_partition)

    return {
        "translated": translated,
        "skipped": skipped,
        "warnings": warnings,
        "probe_decision": decision.value,
        "probe_hit_tokens": probe_hits,
        "probe_ratio": (probe_hits / expected) if expected else 0.0,
        "assembled": assembled,
        "re_probed": re_probed,
        "partition_concurrency": partition_gate.limit,
        "style_capsule_version": capsule.version_label(),
        "style_capsule_hash": capsule.content_hash(),
        "style_capsule": capsule,
        "rewarmed": rewarmed,
        "prefix_hash": prefix_hash,
    }
