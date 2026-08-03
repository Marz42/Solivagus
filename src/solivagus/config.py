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
    chunk_chars: int = 12000
    timeout_seconds: int = 300
    retries: int = 3
    temperature: float = 0.1
    send_temperature: bool = True
    thinking: Literal["disabled"] = "disabled"


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
