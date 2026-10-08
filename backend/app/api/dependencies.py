"""FastAPI dependency wiring: build a provider and use case from settings."""

from __future__ import annotations

from fastapi import Depends
from functools import lru_cache

from stepcheck_providers import VisionProvider, create_provider

from ..application import VerifyProcedureUseCase
from ..config import Settings, get_settings


@lru_cache(maxsize=1)
def get_local_provider(model: str) -> VisionProvider:
    """Reuse the loaded GPU weights across status checks and uploads."""
    return create_provider("qwen-local", model=model)


def get_provider(settings: Settings = Depends(get_settings)) -> VisionProvider:
    """Instantiate the configured provider, passing credentials it may need."""
    kwargs: dict[str, object] = {}
    if settings.provider == "openai":
        kwargs = {"api_key": settings.openai_api_key, "model": settings.model}
    elif settings.provider == "qwen-local":
        return get_local_provider(settings.local_model)
    return create_provider(settings.provider, **kwargs)


def get_verify_use_case(
    provider: VisionProvider = Depends(get_provider),
) -> VerifyProcedureUseCase:
    return VerifyProcedureUseCase(provider)
