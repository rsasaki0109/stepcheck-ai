"""Shared contract types exchanged between the application and any vision provider.

These types are intentionally model-agnostic: they describe *what* is being verified
(steps + images) and *what* a verdict looks like, without assuming anything about the
model that produces the verdict (VLM, JEPA, a video encoder, a human, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    """Outcome of verifying a single procedure step against the images."""

    COMPLETED = "completed"  # ✅ the step is visibly done
    NOT_DONE = "not_done"  # ❌ the step is visibly not done
    UNKNOWN = "unknown"  # ⚠️ cannot be determined from the given images

    @property
    def symbol(self) -> str:
        return {"completed": "✅", "not_done": "❌", "unknown": "⚠️"}[self.value]


@dataclass(frozen=True)
class ProcedureStep:
    """A single, ordered instruction to verify.

    ``index`` is 1-based to match how humans refer to steps ("Step 1").
    """

    index: int
    text: str


@dataclass(frozen=True)
class ImagePayload:
    """One image to be analysed, kept as raw bytes plus its media type.

    Bytes (not paths or URLs) keep providers decoupled from where the image came
    from — an upload, a frame extracted from a video, a page rendered from a PDF.
    """

    data: bytes
    media_type: str = "image/png"


@dataclass(frozen=True)
class VerificationInput:
    """Everything a provider needs to produce verdicts for one procedure run."""

    steps: list[ProcedureStep]
    images: list[ImagePayload]
    context: str | None = None  # optional free-form hint (e.g. domain, language)


@dataclass(frozen=True)
class StepVerdict:
    """A provider's judgement for a single step.

    ``confidence`` is a 0.0–1.0 self-reported score. ``reason`` is a short,
    human-readable justification that the UI shows to the operator.
    """

    index: int
    status: StepStatus
    confidence: float
    reason: str
    evidence: list[str] = field(default_factory=list)  # optional pointers, e.g. image ids

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
