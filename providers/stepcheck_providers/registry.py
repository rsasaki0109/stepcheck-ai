"""A tiny registry so providers can be selected by name at runtime.

Adding a model backend is: subclass :class:`VisionProvider`, decorate it with
``@register_provider("my-model")``, and import the module. No application code
changes.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import VisionProvider

_REGISTRY: dict[str, type[VisionProvider]] = {}


def register_provider(name: str) -> Callable[[type[VisionProvider]], type[VisionProvider]]:
    """Class decorator that registers a provider under ``name``."""

    def decorator(cls: type[VisionProvider]) -> type[VisionProvider]:
        key = name.lower()
        if key in _REGISTRY:
            raise ValueError(f"provider '{name}' is already registered")
        cls.name = key
        _REGISTRY[key] = cls
        return cls

    return decorator


def available_providers() -> list[str]:
    """Names of all registered providers, sorted."""
    return sorted(_REGISTRY)


def create_provider(name: str, **kwargs: object) -> VisionProvider:
    """Instantiate a registered provider by name.

    Extra keyword arguments are forwarded to the provider's constructor (api key,
    model name, etc.).
    """
    key = name.lower()
    if key not in _REGISTRY:
        raise KeyError(
            f"unknown provider '{name}'. Available: {', '.join(available_providers()) or '(none)'}"
        )
    return _REGISTRY[key](**kwargs)
