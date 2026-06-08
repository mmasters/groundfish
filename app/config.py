"""Application settings, loaded from environment variables (prefix ``STOCKFISH_``)."""

from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_pool_size() -> int:
    return min(os.cpu_count() or 1, 4)


class Settings(BaseSettings):
    """Runtime configuration.

    Every field can be overridden via an environment variable named
    ``STOCKFISH_<FIELD>`` (e.g. ``STOCKFISH_ENGINE_POOL_SIZE=8``).
    """

    model_config = SettingsConfigDict(
        env_prefix="STOCKFISH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Engine ---
    engine_path: str = "/usr/local/bin/stockfish"
    engine_pool_size: int = Field(default_factory=_default_pool_size, ge=1)
    engine_hash_mb: int = Field(default=64, ge=1)

    # --- Search limits (also DoS guards; movetime is in milliseconds) ---
    default_movetime_ms: int = Field(default=600, ge=1)
    min_movetime_ms: int = Field(default=50, ge=1)
    max_movetime_ms: int = Field(default=2000, ge=1)

    # --- Timeouts (seconds) ---
    engine_timeout_margin_s: float = Field(default=2.0, ge=0.0)
    pool_acquire_timeout_s: float = Field(default=5.0, ge=0.0)
    engine_start_timeout_s: float = Field(default=20.0, ge=0.0)

    # --- Logging ---
    log_file: str = "./logs/groundfish.log"
    log_level: str = "INFO"
    log_to_stdout: bool = True
    log_max_bytes: int = Field(default=10 * 1024 * 1024, ge=0)
    log_backup_count: int = Field(default=5, ge=0)

    # --- Difficulty presets: name -> (skill_level, movetime_ms) ---
    # Mirrors the mapping both client apps use today (Easy/Medium/Hard).
    @property
    def difficulty_presets(self) -> dict[str, tuple[int, int]]:
        return {
            "easy": (2, 200),
            "medium": (9, 600),
            "hard": (20, 1200),
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
