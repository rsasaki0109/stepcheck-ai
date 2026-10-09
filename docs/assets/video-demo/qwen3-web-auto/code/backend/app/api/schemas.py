"""Pydantic schemas for the HTTP API (the interface layer's DTOs)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

from ..domain import VerificationReport
from stepcheck_providers.reference_flow import ReferenceFlow


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


class VideoActionOut(BaseModel):
    id: int
    label: str
    reason: str
    uncertainty: str
    evidence_seconds: list[float]
    first_seen_seconds: float
    last_seen_seconds: float


class FlowTransitionOut(BaseModel):
    from_: int = Field(alias="from")
    to: int
    status: Literal["sampled_before", "ambiguous"]
    reason: str


class VideoFrameOut(BaseModel):
    timestamp_seconds: float
    image_url: str


class VideoFlowOut(BaseModel):
    title: str
    provider: str
    model: str
    analysis_mode: Literal["live", "recorded_demo"]
    source_sha256: str
    duration_seconds: float
    sample_interval_seconds: float
    expected_procedure_supplied: bool
    actions: list[VideoActionOut]
    transitions: list[FlowTransitionOut]
    sampled_seconds: list[float]
    frames: list[VideoFrameOut]
    limitations: list[str]
    time_note: str


class ReferenceStepOut(BaseModel):
    step_id: str
    index: int
    label: str
    status: Literal["observed", "unknown"]
    reason: str
    uncertainty: str
    evidence_seconds: list[float]


class ReferenceTransitionOut(BaseModel):
    from_: str = Field(alias="from")
    to: str
    status: Literal["sampled_before", "unknown", "violated"]


class ReferencePassOut(BaseModel):
    steps: list[ReferenceStepOut]
    transitions: list[ReferenceTransitionOut]
    order_status: Literal["supported_sample_order", "unknown", "violated"]
    sampled_seconds: list[float] | None = None
    sample_interval_seconds: float | None = None


class VideoReferenceOut(ReferencePassOut):
    title: str
    reference: ReferenceFlow
    provider: str
    model: str
    analysis_mode: Literal["live", "recorded_demo"]
    source_sha256: str
    duration_seconds: float
    sample_interval_seconds: float | None
    expected_procedure_supplied: Literal[True]
    sampled_seconds: list[float]
    frames: list[VideoFrameOut]
    time_note: str
    scope_note: str
    initial: ReferencePassOut | None = None
    workflow: dict | None = None
    refinement: dict | None = None
    source_credit: str | None = None
