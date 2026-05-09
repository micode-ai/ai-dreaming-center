"""Global config — Pydantic-settings + config.yaml + DC_* env vars."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


CONFIG_PATH = Path("config.yaml")


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DC_", extra="ignore")

    # Database
    db_path: str = "data/dreaming.db"

    # Projects
    projects_root: str = ""
    default_locale: str = "ru"

    # Server
    host: str = "0.0.0.0"
    port: int = 8086

    # Claude CLI (defaults; overridable per-project)
    claude_path: str = "claude"

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(**_load_yaml())


def settings() -> AppSettings:
    return AppSettings.load()
