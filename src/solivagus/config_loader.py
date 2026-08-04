"""Load YAML config into Settings (single reproducible entry point)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from solivagus.config import Settings


class ConfigLoadError(ValueError):
    pass


def load_yaml_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ConfigLoadError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"invalid YAML: {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigLoadError(f"config root must be a mapping: {path}")
    return data


def apply_config_dict(settings: Settings, data: dict[str, Any]) -> Settings:
    """Apply nested YAML profile onto a Settings instance (mutates and returns it)."""
    if "workspace" in data and data["workspace"]:
        settings.workspace = Path(str(data["workspace"])).expanduser()
    if "batch_dir" in data and data["batch_dir"]:
        settings.batch_dir = Path(str(data["batch_dir"])).expanduser()

    provider = data.get("provider") or {}
    if isinstance(provider, dict):
        if provider.get("base_url"):
            settings.llm_api_base = str(provider["base_url"])
        if provider.get("model"):
            settings.llm_model = str(provider["model"])
        if provider.get("repair_model"):
            settings.repair_model = str(provider["repair_model"])
        if provider.get("temperature") is not None:
            settings.temperature = float(provider["temperature"])
        if provider.get("timeout_seconds") is not None:
            settings.timeout_seconds = int(provider["timeout_seconds"])
        if provider.get("thinking"):
            settings.thinking = "disabled"  # only supported mode

    translation = data.get("translation") or {}
    if isinstance(translation, dict):
        if translation.get("target_language"):
            settings.target_language = str(translation["target_language"])
        if translation.get("chunk_chars") is not None:
            settings.chunk_chars = int(translation["chunk_chars"])
        if translation.get("strict") is not None:
            settings.qa_strict = bool(translation["strict"])
        if translation.get("references_mode"):
            settings.references_mode = str(translation["references_mode"])  # type: ignore[assignment]
        if translation.get("html_table_mode"):
            settings.html_table_mode = str(translation["html_table_mode"])  # type: ignore[assignment]

    planning = data.get("planning") or {}
    if isinstance(planning, dict):
        for src, dst in (
            ("unit_target_tokens", "unit_target_tokens"),
            ("unit_max_tokens", "unit_max_tokens"),
            ("unit_min_tokens", "unit_min_tokens"),
            ("first_partition_tokens", "first_partition_tokens"),
            ("partition_target_tokens", "partition_target_tokens"),
            ("partition_max_tokens", "partition_max_tokens"),
        ):
            if planning.get(src) is not None:
                setattr(settings, dst, int(planning[src]))
        price = planning.get("price") or {}
        if isinstance(price, dict):
            if price.get("cache_hit_per_million") is not None:
                settings.price_cache_hit_per_million = float(price["cache_hit_per_million"])
            if price.get("cache_miss_per_million") is not None:
                settings.price_cache_miss_per_million = float(price["cache_miss_per_million"])
            if price.get("output_per_million") is not None:
                settings.price_output_per_million = float(price["output_per_million"])

    cache = data.get("cache") or {}
    if isinstance(cache, dict):
        if cache.get("target_mode"):
            settings.target_mode = str(cache["target_mode"])  # type: ignore[assignment]
        if cache.get("prompt_version"):
            settings.prompt_version = str(cache["prompt_version"])
        if cache.get("probe_min_ratio") is not None:
            settings.cache_probe_min_ratio = float(cache["probe_min_ratio"])
        if cache.get("warning_ratio") is not None:
            settings.cache_warning_ratio = float(cache["warning_ratio"])
        if cache.get("settle_seconds") is not None:
            settings.cache_settle_seconds = float(cache["settle_seconds"])
        if cache.get("enable_local_translation_cache") is not None:
            settings.enable_local_translation_cache = bool(
                cache["enable_local_translation_cache"]
            )

    concurrency = data.get("concurrency") or {}
    if isinstance(concurrency, dict):
        mapping = {
            "global": "global_concurrency",
            "per_document": "per_document_concurrency",
            "per_partition": "per_partition_concurrency",
            "max_global": "max_global_concurrency",
            "low_probe": "low_probe_concurrency",
            "adaptive": "adaptive_concurrency",
        }
        for src, dst in mapping.items():
            if concurrency.get(src) is not None:
                val = concurrency[src]
                setattr(settings, dst, bool(val) if dst == "adaptive_concurrency" else int(val))

    qa = data.get("qa") or {}
    if isinstance(qa, dict):
        mapping = {
            "enabled": "qa_enabled",
            "numerical_check": "qa_numerical_check",
            "structure_check": "qa_structure_check",
            "citation_check": "qa_citation_check",
            "terminology_check": "qa_terminology_check",
            "auto_repair": "qa_auto_repair",
            "max_repair_attempts": "qa_max_repair_attempts",
            "strict": "qa_strict",
        }
        for src, dst in mapping.items():
            if qa.get(src) is not None:
                val = qa[src]
                if dst == "qa_max_repair_attempts":
                    setattr(settings, dst, int(val))
                else:
                    setattr(settings, dst, bool(val))
        if qa.get("repair_model"):
            settings.repair_model = str(qa["repair_model"])

    ocr = data.get("ocr") or {}
    if isinstance(ocr, dict):
        if ocr.get("pipeline_version"):
            settings.ocr_pipeline_version = str(ocr["pipeline_version"])
        if ocr.get("device") is not None:
            settings.ocr_device = str(ocr["device"]) if ocr["device"] else None
        if ocr.get("batch_pages") is not None:
            settings.ocr_batch_pages = int(ocr["batch_pages"])
        if ocr.get("orientation") is not None:
            settings.ocr_use_orientation = bool(ocr["orientation"])
        if ocr.get("unwarping") is not None:
            settings.ocr_use_unwarping = bool(ocr["unwarping"])
        if ocr.get("chart_recognition") is not None:
            settings.ocr_use_chart_recognition = bool(ocr["chart_recognition"])
        if ocr.get("drop_footnotes") is not None:
            settings.ocr_drop_footnotes = bool(ocr["drop_footnotes"])
        if ocr.get("drop_aside_text") is not None:
            settings.ocr_drop_aside_text = bool(ocr["drop_aside_text"])
        # keep_footnotes / keep_aside_text aliases (brief §25)
        if ocr.get("keep_footnotes") is not None:
            settings.ocr_drop_footnotes = not bool(ocr["keep_footnotes"])
        if ocr.get("keep_aside_text") is not None:
            settings.ocr_drop_aside_text = not bool(ocr["keep_aside_text"])

    return settings


def load_settings_from_config(
    path: Path,
    *,
    env_file: str | None = None,
) -> Settings:
    from solivagus.config import get_settings

    settings = get_settings(env_file)
    apply_config_dict(settings, load_yaml_file(path))
    return settings
