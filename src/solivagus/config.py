from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_api_base: str = Field(
        default="https://api.deepseek.com",
        validation_alias="LLM_API_BASE",
    )
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias="LLM_MODEL",
    )
    workspace: Path = Field(
        default_factory=lambda: Path.cwd(),
        validation_alias="SOLIVAGUS_WORKSPACE",
    )
    batch_dir: Path = Field(
        default=Path(r"D:\PDFS"),
        validation_alias="SOLIVAGUS_BATCH_DIR",
    )
    target_language: str = "简体中文"
    chunk_chars: int = 12000  # Phase 2 OCR provisional seeds only
    timeout_seconds: int = 300
    retries: int = 3
    temperature: float = 0.1
    send_temperature: bool = True
    thinking: Literal["disabled"] = "disabled"

    # Planning (Phase 3)
    unit_target_tokens: int = 12_000
    unit_max_tokens: int = 24_000
    unit_min_tokens: int = 1_500
    first_partition_tokens: int = 96_000
    partition_target_tokens: int = 220_000
    partition_max_tokens: int = 300_000
    price_cache_hit_per_million: float = 0.02
    price_cache_miss_per_million: float = 1.00
    price_output_per_million: float = 2.00

    # Provider / KV cache (Phase 4)
    prompt_version: str = "translate-v1"
    target_mode: Literal["repeat", "id_only"] = "repeat"
    cache_probe_min_ratio: float = 0.70
    cache_warning_ratio: float = 0.50
    cache_settle_seconds: float = 0.0
    enable_local_translation_cache: bool = True

    # Concurrency (Phase 5)
    global_concurrency: int = 16
    per_document_concurrency: int = 8
    per_partition_concurrency: int = 8
    max_global_concurrency: int = 64
    low_probe_concurrency: int = 2
    adaptive_concurrency: bool = True

    # OCR
    ocr_pipeline_version: str = "v1.6"
    ocr_device: str | None = Field(default=None, validation_alias="SOLIVAGUS_OCR_DEVICE")
    ocr_batch_pages: int = 8
    ocr_use_orientation: bool = False
    ocr_use_unwarping: bool = False
    ocr_use_chart_recognition: bool = False


@lru_cache(maxsize=4)
def get_settings(env_file: str | None = None) -> Settings:
    if env_file:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    explicit = os.environ.get("SOLIVAGUS_ENV_FILE")
    if explicit:
        return Settings(_env_file=explicit)  # type: ignore[call-arg]
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
