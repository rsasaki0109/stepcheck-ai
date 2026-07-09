"""Application use case: verify a procedure against images using a vision provider.

This orchestrates the flow and depends only on the ``VisionProvider`` abstraction —
never on a concrete model. That is the seam that keeps StepCheck model-agnostic.
"""

from __future__ import annotations

from stepcheck_providers import (
    ImagePayload,
    StepStatus,
    StepVerdict,
    VerificationInput,
    VisionProvider,
)

from ..domain import (
    Procedure,
    StepResult,
    VerificationReport,
    VerificationSummary,
)
from .markdown_parser import parse_procedure


class VerifyProcedureUseCase:
    """Parse a procedure, ask a provider to verify it, and assemble a report."""

    def __init__(self, provider: VisionProvider) -> None:
        self._provider = provider

    async def execute(
        self,
        *,
        markdown: str,
        images: list[ImagePayload],
        context: str | None = None,
    ) -> VerificationReport:
        procedure = parse_procedure(markdown)
        verdicts = await self._provider.verify(
            VerificationInput(steps=procedure.steps, images=images, context=context)
        )
        results = _match_verdicts_to_steps(procedure, verdicts)
        return VerificationReport(
            provider=self._provider.name,
            procedure_title=procedure.title,
            results=results,
            summary=VerificationSummary.from_results(results),
        )


def _match_verdicts_to_steps(
    procedure: Procedure, verdicts: list[StepVerdict]
) -> list[StepResult]:
    """Key verdicts by step index; fill any missing step with an 'unknown' verdict."""
    by_index = {verdict.index: verdict for verdict in verdicts}
    results: list[StepResult] = []
    for step in procedure.steps:
        verdict = by_index.get(
            step.index,
            StepVerdict(
                index=step.index,
                status=StepStatus.UNKNOWN,
                confidence=0.0,
                reason="The provider returned no verdict for this step.",
            ),
        )
        results.append(StepResult(step=step, verdict=verdict))
    return results
