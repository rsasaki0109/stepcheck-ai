"""StepCheck AI — model-agnostic vision provider contracts and implementations."""

from __future__ import annotations

from .base import VisionProvider
from .registry import available_providers, create_provider, register_provider
from .types import (
    ImagePayload,
    ProcedureStep,
    StepStatus,
    StepVerdict,
    VerificationInput,
)

# Importing the modules registers the providers as a side effect.
from . import mock_provider  # noqa: E402,F401
from . import openai_provider  # noqa: E402,F401

__all__ = [
    "VisionProvider",
    "register_provider",
    "create_provider",
    "available_providers",
    "ImagePayload",
    "ProcedureStep",
    "StepStatus",
    "StepVerdict",
    "VerificationInput",
]
