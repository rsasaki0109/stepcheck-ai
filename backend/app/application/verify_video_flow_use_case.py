"""Review a given reference against real sampled video images; preserve unknowns."""

import base64

from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import FlowInferenceError
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment, build_reference_flow

from ..infrastructure.video import SampledVideo


def reference_report_with_frames(reference: ReferenceFlow, judgment: ReferenceJudgment,
                                  sampled: SampledVideo, *, provider: str, source_sha256: str,
                                  analysis_mode: str, model: str) -> dict:
    try:
        report = build_reference_flow(reference, judgment,
            [f.timestamp_seconds for f in sampled.frames], sampled.duration_seconds)
    except ValueError as exc:
        raise FlowInferenceError(f"Invalid reference judgment: {exc}") from exc
    return {**report, "provider": provider, "model": model, "analysis_mode": analysis_mode,
        "source_sha256": source_sha256, "duration_seconds": sampled.duration_seconds,
        "sample_interval_seconds": sampled.sample_interval_seconds,
        "frames": [{"timestamp_seconds": f.timestamp_seconds,
            "image_url": f"data:{f.image.media_type};base64," + base64.b64encode(f.image.data).decode("ascii")}
            for f in sampled.frames], "sampled_seconds": sorted({f.timestamp_seconds for f in sampled.frames}),
        "initial": None, "workflow": None}


class VerifyVideoFlowUseCase:
    def __init__(self, provider: VisionProvider, model: str):
        self.provider, self.model = provider, model

    async def execute(self, reference: ReferenceFlow, sampled: SampledVideo, source_sha256: str) -> dict:
        judgment = await self.provider.verify_reference_flow(reference, sampled.frames, sampled.duration_seconds)
        return reference_report_with_frames(reference, judgment, sampled, provider=self.provider.name,
            source_sha256=source_sha256, analysis_mode="live", model=self.model)
