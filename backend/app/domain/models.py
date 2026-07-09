"""Domain layer: the core entities of StepCheck, independent of web or model concerns.

Verdict-level value objects (``StepStatus``, ``StepVerdict``) come from the
``stepcheck_providers`` contract package, which acts as the shared kernel between the
application and any model backend. The aggregates below (procedure, per-step result,
report) are owned by the application and add the structure the API and UI need.
"""

from __future__ import annotations

from dataclasses import dataclass

from stepcheck_providers import ProcedureStep, StepStatus, StepVerdict


@dataclass(frozen=True)
class Procedure:
    """A parsed work procedure: a title plus an ordered list of steps."""

    title: str
    steps: list[ProcedureStep]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("a procedure must contain at least one step")


@dataclass(frozen=True)
class StepResult:
    """A step paired with the provider's verdict for it."""

    step: ProcedureStep
    verdict: StepVerdict

    @property
    def status(self) -> StepStatus:
        return self.verdict.status


@dataclass(frozen=True)
class VerificationSummary:
    """Aggregate counts across all steps in a report."""

    total: int
    completed: int
    not_done: int
    unknown: int

    @classmethod
    def from_results(cls, results: list[StepResult]) -> "VerificationSummary":
        counts = {status: 0 for status in StepStatus}
        for result in results:
            counts[result.status] += 1
        return cls(
            total=len(results),
            completed=counts[StepStatus.COMPLETED],
            not_done=counts[StepStatus.NOT_DONE],
            unknown=counts[StepStatus.UNKNOWN],
        )


@dataclass(frozen=True)
class VerificationReport:
    """The full outcome of verifying a procedure against a set of images."""

    provider: str
    procedure_title: str
    results: list[StepResult]
    summary: VerificationSummary
