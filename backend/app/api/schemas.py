"""Pydantic schemas for the HTTP API (the interface layer's DTOs)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain import VerificationReport


class StepResultOut(BaseModel):
    index: int = Field(..., description="1-based step number")
    text: str = Field(..., description="The step instruction")
    status: str = Field(..., description="completed | not_done | unknown")
    symbol: str = Field(..., description="Emoji for the status (✅ ❌ ⚠️)")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str


class SummaryOut(BaseModel):
    total: int
    completed: int
    not_done: int
    unknown: int


class VerificationReportOut(BaseModel):
    provider: str
    procedure_title: str
    summary: SummaryOut
    steps: list[StepResultOut]

    @classmethod
    def from_domain(cls, report: VerificationReport) -> "VerificationReportOut":
        return cls(
            provider=report.provider,
            procedure_title=report.procedure_title,
            summary=SummaryOut(
                total=report.summary.total,
                completed=report.summary.completed,
                not_done=report.summary.not_done,
                unknown=report.summary.unknown,
            ),
            steps=[
                StepResultOut(
                    index=result.step.index,
                    text=result.step.text,
                    status=result.verdict.status.value,
                    symbol=result.verdict.status.symbol,
                    confidence=result.verdict.confidence,
                    reason=result.verdict.reason,
                )
                for result in report.results
            ],
        )


class ProvidersOut(BaseModel):
    active: str
    available: list[str]
