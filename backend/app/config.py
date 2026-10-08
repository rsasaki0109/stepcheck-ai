"""Application configuration, loaded from environment variables (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STEPCHECK_", env_file=".env", extra="ignore"
    )

    #: Name of the provider to use (must be registered in stepcheck_providers).
    provider: str = "mock"

    #: Model identifier passed to the provider (provider-specific).
    model: str = "gpt-4o"
    local_model: str = "Qwen/Qwen2.5-VL-3B-Instruct"

    #: Credentials for hosted providers. Read directly (no prefix) for convenience.
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    #: Upload limits.
    max_images: int = 8
    max_image_bytes: int = 10 * 1024 * 1024  # 10 MiB per image
    max_video_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_video_seconds: float = Field(default=120, gt=0)
    max_video_frames: int = Field(default=48, ge=2, le=96)

    #: CORS origins allowed to call the API (comma-separated in the env var).
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
