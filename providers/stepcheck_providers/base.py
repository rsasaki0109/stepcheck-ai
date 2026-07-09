"""The provider abstraction every model backend must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import StepVerdict, VerificationInput


class VisionProvider(ABC):
    """Contract for turning (steps, images) into per-step verdicts.

    Implementations may call a hosted VLM, run a local model, query a JEPA-style
    representation model, or anything else. The application only ever sees this
    interface, so backends are fully interchangeable.
    """

    #: Stable identifier used for registration and selection (e.g. "openai").
    name: str = "base"

    @abstractmethod
    async def verify(self, request: VerificationInput) -> list[StepVerdict]:
        """Return exactly one :class:`StepVerdict` per step in ``request.steps``.

        Implementations must return verdicts covering every step. Ordering by
        ``index`` is recommended but callers should not rely on it — the
        application keys results by ``StepVerdict.index``.
        """
        raise NotImplementedError

    async def health(self) -> bool:
        """Lightweight readiness check (e.g. credentials present). Override as needed."""
        return True
