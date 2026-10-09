"""Review a given reference against real sampled video images; preserve unknowns."""

import base64
import asyncio
import hashlib
from pathlib import Path

from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import FlowInferenceError
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment, build_reference_flow
from stepcheck_providers.reference_refinement import POLICY, fit_refinement_budget, validate_options

from ..infrastructure.video import SampledVideo, read_video_frame


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

    async def execute(self, reference: ReferenceFlow, sampled: SampledVideo, source_sha256: str, *,
                      video: Path | None = None, auto_refine: bool = False,
                      refinement_interval: float = 0.25, max_frames: int = 24) -> dict:
        if auto_refine:
            validate_options(refinement_interval, max_frames)
            if video is None:
                raise FlowInferenceError("Automatic refinement requires the source video.")
            await check_source(video, source_sha256)
        judgment = await self.provider.verify_reference_flow(reference, sampled.frames, sampled.duration_seconds)
        initial = reference_report_with_frames(reference, judgment, sampled, provider=self.provider.name,
            source_sha256=source_sha256, analysis_mode="live", model=self.model)
        if not auto_refine:
            return initial
        await check_source(video, source_sha256)
        selection = {"plan": None, "chosen_interval_seconds": None, "attempts": [], "stop_reason": "no_unknown_steps"}
        unknown_ids = [s["step_id"] for s in initial["steps"] if s["status"] == "unknown"]
        if unknown_ids:
            selection = fit_refinement_budget(initial["steps"], initial["sampled_seconds"],
                sampled.duration_seconds, refinement_interval, max_frames)
        report, calls = initial, 1
        plan = selection["plan"]
        if plan is not None:
            by_time = {f.timestamp_seconds: f for f in sampled.frames}
            for t in plan["added_seconds"]:
                by_time[t] = await asyncio.to_thread(read_video_frame, video, t)
            followup_frames = [by_time[t] for t in plan["sampled_seconds"]]
            await check_source(video, source_sha256)
            target = reference.model_copy(update={"steps": [s for s in reference.steps if s.id in unknown_ids]})
            answer = await self.provider.verify_reference_flow(target, followup_frames, sampled.duration_seconds)
            await check_source(video, source_sha256)
            try:
                # Validate against THIS pass, including only the unknown target IDs.
                build_reference_flow(target, answer, plan["sampled_seconds"], sampled.duration_seconds)
            except ValueError as exc:
                raise FlowInferenceError(f"Invalid follow-up judgment: {exc}") from exc
            replacement = {o.step_id: o for o in answer.observations}
            merged = ReferenceJudgment(observations=[replacement.get(o.step_id, o) for o in judgment.observations])
            union = SampledVideo(sampled.duration_seconds, [by_time[t] for t in sorted(by_time)], None)
            report = reference_report_with_frames(reference, merged, union, provider=self.provider.name,
                source_sha256=source_sha256, analysis_mode="live", model=self.model)
            report["refinement"] = plan
            calls = 2
            stop = "unknown_after_followup" if any(s["status"] == "unknown" for s in report["steps"]) else "no_unknown_steps"
        else:
            stop = selection["stop_reason"]
        return {**report, "initial": {key: initial[key] for key in
            ("steps", "transitions", "order_status", "sampled_seconds", "sample_interval_seconds")},
            "workflow": {"sampling_requests": calls, "stop_reason": stop,
                "unknown_step_ids": [s["step_id"] for s in report["steps"] if s["status"] == "unknown"],
                "requested_refinement_interval_seconds": refinement_interval, "max_frames": max_frames,
                "interval_selection": selection, "policy": POLICY}}


async def check_source(video: Path, expected: str):
    def digest():
        sha = hashlib.sha256()
        with video.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()
    if await asyncio.to_thread(digest) != expected:
        raise FlowInferenceError("Source video changed during verification; retry with the original file.")
