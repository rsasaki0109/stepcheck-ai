"""Ask a vision provider for actions and attach only real supporting video frames."""

import base64

from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import Detection, FlowInferenceError, build_flow

from ..infrastructure.video import SampledVideo


def report_with_frames(detection: Detection, sampled: SampledVideo, *, provider: str,
                       source_sha256: str, analysis_mode: str, model: str) -> dict:
    try:
        report = build_flow(detection, [frame.timestamp_seconds for frame in sampled.frames], sampled.duration_seconds)
    except ValueError as exc:
        raise FlowInferenceError("Recognition returned evidence from a frame that was not sampled.") from exc
    return {**report, "provider": provider, "model": model, "analysis_mode": analysis_mode,
            "source_sha256": source_sha256, "duration_seconds": sampled.duration_seconds,
            "sample_interval_seconds": sampled.sample_interval_seconds,
            "expected_procedure_supplied": False,
            "frames": [{"timestamp_seconds": frame.timestamp_seconds,
                        "image_url": f"data:{frame.image.media_type};base64," +
                        base64.b64encode(frame.image.data).decode("ascii")}
                       for frame in sampled.frames]}


class DiscoverFlowUseCase:
    def __init__(self, provider: VisionProvider, model: str):
        self.provider = provider
        self.model = model

    async def execute(self, sampled: SampledVideo, source_sha256: str) -> dict:
        detection = await self.provider.discover_flow(sampled.frames, sampled.duration_seconds)
        return report_with_frames(detection, sampled, provider=self.provider.name,
                                  source_sha256=source_sha256, analysis_mode="live", model=self.model)
