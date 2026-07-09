"""A deterministic, dependency-free provider for tests, CI and offline demos.

It does not look at image contents. Instead it produces a stable, varied mix of
statuses so the full pipeline and UI can be exercised without any API key.
"""

from __future__ import annotations

from .base import VisionProvider
from .registry import register_provider
from .types import StepStatus, StepVerdict, VerificationInput

# Rotating pattern so the UI shows every status; deterministic per step index.
_PATTERN: tuple[tuple[StepStatus, float], ...] = (
    (StepStatus.COMPLETED, 0.97),
    (StepStatus.COMPLETED, 0.88),
    (StepStatus.NOT_DONE, 0.82),
    (StepStatus.UNKNOWN, 0.40),
)


@register_provider("mock")
class MockProvider(VisionProvider):
    """Returns fixed, reproducible verdicts derived from the step index."""

    async def verify(self, request: VerificationInput) -> list[StepVerdict]:
        if not request.images:
            # No evidence at all -> everything is undeterminable.
            return [
                StepVerdict(
                    index=step.index,
                    status=StepStatus.UNKNOWN,
                    confidence=0.0,
                    reason="No images were provided, so this step cannot be verified.",
                )
                for step in request.steps
            ]

        verdicts: list[StepVerdict] = []
        for i, step in enumerate(request.steps):
            status, confidence = _PATTERN[i % len(_PATTERN)]
            verdicts.append(
                StepVerdict(
                    index=step.index,
                    status=status,
                    confidence=confidence,
                    reason=(
                        f"[mock] Deterministic verdict for step {step.index} "
                        f'("{step.text}") based on {len(request.images)} image(s). '
                        "Replace with a real provider (e.g. openai) for genuine analysis."
                    ),
                )
            )
        return verdicts
