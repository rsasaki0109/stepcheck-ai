"""Local stdio MCP tools: video -> image content -> host vision review -> JSON.

The MCP server extracts frames; the connected vision-capable host judges them.
Open-ended detection requests host vision inference through MCP sampling.
"""

from __future__ import annotations

import hashlib
import base64
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Annotated, Literal

from mcp.server.mcpserver import Image, MCPServer, Resolve, Sample
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CreateMessageResult, SamplingMessage, TextContent, ImageContent
from PIL import Image as PILImage, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from check_video_flow import check_flow as compare_flow
from video_discovery import Detection, build_flow
from verify_qwen3_video_flow import compare_order

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
VIDEO = Path(os.environ.get("STEPCHECK_DEMO_VIDEO", str(ASSETS / "source.webm")))
REVIEW = Path(os.environ.get("STEPCHECK_DEMO_REVIEW", str(ASSETS / "review.json")))
DETECTED_FLOW = Path(os.environ.get("STEPCHECK_DETECTED_FLOW", str(ASSETS / "detected-flow.json")))
PROCEDURE = ROOT / "examples" / "handwashing.md"
REFERENCE_REVIEW = Path(os.environ.get("STEPCHECK_REFERENCE_REVIEW",
    str(ASSETS / "codex-reference-verification" / "verification.json")))
mcp = MCPServer("StepCheck video vision review")


def video_info() -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
         "-of", "json", str(VIDEO)], capture_output=True, check=True, timeout=30,
    )
    data = json.loads(result.stdout)
    stream = next(stream for stream in data["streams"] if "width" in stream)
    return {"duration_seconds": float(data["format"]["duration"]),
            "width": stream["width"], "height": stream["height"]}


def steps() -> list[str]:
    return re.findall(r"^\d+\. (.+)$", PROCEDURE.read_text(encoding="utf-8"), re.MULTILINE)


def frame_bytes(timestamp_seconds: float) -> bytes:
    duration = video_info()["duration_seconds"]
    if not math.isfinite(timestamp_seconds) or not 0 <= timestamp_seconds < duration:
        raise ToolError(f"Timestamp must be finite and in [0, {duration}).")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(timestamp_seconds),
         "-i", str(VIDEO), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True, timeout=30,
    )
    if not result.stdout:
        raise ToolError("No frame could be decoded at that timestamp.")
    return result.stdout


def sample_times(sample_interval_seconds: float) -> list[float]:
    duration = video_info()["duration_seconds"]
    if not math.isfinite(sample_interval_seconds) or sample_interval_seconds <= 0:
        raise ToolError("Sampling interval must be finite and positive.")
    count = math.ceil(duration / sample_interval_seconds)
    if count + 1 > 96:
        raise ToolError("At most 96 frames per request. Increase sample_interval_seconds for longer videos.")
    return sorted(set([round(i * sample_interval_seconds, 6) for i in range(count)] +
                      [round(max(0, duration - 0.1), 6)]))


def image_sample_request(prompt: str, times: list[float]) -> Sample:
    """Build chronological contact sheets from actual decoded source frames."""
    blocks = [TextContent(type="text", text=prompt)]
    label_font = ImageFont.load_default(size=20)
    for start in range(0, len(times), 12):
        page_times = times[start:start + 12]
        sheet = PILImage.new("RGB", (960, 4 * 266), "#111827")
        draw = ImageDraw.Draw(sheet)
        for index, timestamp in enumerate(page_times):
            frame = PILImage.open(io.BytesIO(frame_bytes(timestamp))).convert("RGB")
            frame.thumbnail((320, 240))
            x, y = (index % 3) * 320, (index // 3) * 266
            sheet.paste(frame, (x + (320 - frame.width) // 2, y + 26))
            draw.text((x + 8, y + 2), f"{timestamp:g} s", fill="white", font=label_font)
        data = io.BytesIO()
        sheet.save(data, format="PNG")
        blocks.append(ImageContent(type="image", mime_type="image/png",
                                   data=base64.b64encode(data.getvalue()).decode()))
    return Sample([SamplingMessage(role="user", content=blocks)], max_tokens=5000,
                  include_context="none", temperature=0)


def discovery_request(sample_interval_seconds: float) -> Sample:
    """Only source images and metadata are sent; no expected procedure is read."""
    times = sample_times(sample_interval_seconds)
    prompt = (
        "Discover the actions and their observed order from this ONE video. No expected procedure is supplied. "
        "Inspect the timestamped images. Use only visible evidence; do not fill in customary missing steps. "
        "Split distinct visible actions, preserve repeated actions as separate occurrences, and mark uncertain "
        "interpretations. Evidence times must be labels actually present in the sheets. Do not claim exact action "
        "boundaries or hidden causal intent. Return ONLY a JSON object matching this schema: "
        '{"title":"short title","actions":[{"label":"short English action name",'
        '"reason":"what is visibly happening","evidence_seconds":[0.0],"uncertainty":""}],'
        '"limitations":["sampling or visibility limitations"]}. '
        "Return an empty actions list if nothing is identifiable. All images are chronological samples, "
        f"not continuous motion. Duration: {video_info()['duration_seconds']} seconds."
    )
    return image_sample_request(prompt, times)


@mcp.tool()
def inspect_video_for_flow() -> dict:
    """Inspect source metadata without loading any expected steps."""
    return {**video_info(), "instructions": "Call detect_flow with a vision-capable sampling host, or inspect read_frame images and call record_detected_flow."}


def save_detected_flow(reviewer: str, detection: Detection, reviewed_seconds: list[float], method: str) -> dict:
    if not reviewer.strip():
        raise ToolError("Identify the host that reviewed the images.")
    try:
        report = build_flow(detection, reviewed_seconds, video_info()["duration_seconds"])
    except ValueError as error:
        raise ToolError(str(error)) from error
    report.update({"reviewer": reviewer, "method": method, "expected_procedure_supplied": False,
                   "source_sha256": hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
                   "duration_seconds": video_info()["duration_seconds"]})
    DETECTED_FLOW.parent.mkdir(parents=True, exist_ok=True)
    DETECTED_FLOW.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


@mcp.tool()
def detect_flow(sample_interval_seconds: float = 0.75,
                completion: Annotated[CreateMessageResult, Resolve(discovery_request)] = None) -> dict:
    """Detect an open-ended action flow from one video through host MCP vision sampling.

    Requires a vision-capable host supporting sampling. Returns and saves observed
    actions, supporting timestamps, and sampled order; no expected flow is supplied.
    """
    if completion is None or completion.content.type != "text":
        raise ToolError("The vision host must return a JSON text response.")
    try:
        detection = Detection.model_validate_json(completion.content.text)
    except ValueError as error:
        raise ToolError(f"Invalid detection JSON: {error}") from error
    return save_detected_flow(completion.model, detection, sample_times(sample_interval_seconds),
                              "MCP sampling: host vision review of timestamped source-frame contact sheets")


@mcp.tool()
def record_detected_flow(reviewer: str, detection: Detection, reviewed_seconds: list[float]) -> dict:
    """Save open-ended actions after the host has visually inspected read_frame results.

    This fallback trusts the host's attestation of inspected timestamps, as does
    record_review. It performs no model inference itself.
    """
    return save_detected_flow(reviewer, detection, reviewed_seconds,
                              "Host-attested visual review of extracted frames; no expected procedure supplied")


class Observation(BaseModel):
    index: int = Field(ge=1)
    status: Literal["completed", "not_done", "unknown"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    evidence_seconds: list[float] = Field(min_length=1)


@mcp.tool()
def inspect_video() -> dict:
    """Get the video metadata, ordered procedure, and vision-review instructions."""
    return {
        **video_info(),
        "steps": [{"index": i + 1, "text": value} for i, value in enumerate(steps())],
        "instructions": (
            "Call read_frame at different timestamps and visually inspect the returned images. "
            "Judge from visible evidence only. A missing view is unknown, not not_done. "
            "Use completed only when the action is supported by the frames. "
            "Confidence is your subjective estimate, not a calibrated probability. "
            "Call record_review with one observation per step and the reviewed evidence timestamps."
        ),
    }


@mcp.tool()
def read_frame(timestamp_seconds: float) -> Image:
    """Return a real video frame as MCP image content for the host model to inspect."""
    return Image(data=frame_bytes(timestamp_seconds), format="png")


class ReferenceObservation(BaseModel):
    model_config = {"extra": "forbid"}
    step_id: str
    status: Literal["observed", "unknown"]
    reason: str = Field(min_length=1)
    evidence_seconds: list[float]
    uncertainty: str = ""


class ReferenceCompletion(BaseModel):
    model_config = {"extra": "forbid"}
    source_sha256: str
    observations: list[ReferenceObservation]


def validate_reference(reference: dict) -> list[dict]:
    given = reference.get("steps")
    if not isinstance(reference.get("title"), str) or not reference["title"].strip():
        raise ToolError("Reference requires a nonempty title.")
    if not isinstance(given, list) or not given or any(not isinstance(s, dict) for s in given):
        raise ToolError("Reference requires a nonempty list of steps.")
    ids = [s.get("id") for s in given]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ToolError("Reference must contain unique nonempty step IDs.")
    if any(not isinstance(s.get("label"), str) or not s["label"].strip() for s in given):
        raise ToolError("Each reference step requires a nonempty label.")
    return given


def reference_request(reference: dict, sample_interval_seconds: float) -> Sample:
    validate_reference(reference)
    source_hash = hashlib.sha256(VIDEO.read_bytes()).hexdigest()
    times = sample_times(sample_interval_seconds)
    prompt = (
        "Visually verify this GIVEN reference against samples from ONE video. "
        "The reference supplies expected labels and visible criteria, not proof that actions occurred. "
        "Inspect each timestamped source image. Return exactly one observation for each step ID. "
        "Use status observed only with visible supporting evidence; otherwise unknown and explain why. "
        "Evidence seconds must be exact labels present in these images. Do not infer absent actions, "
        "repair the requested sequence, claim hidden events, or assign confidence scores. "
        "Do not calculate order: the server derives it from your cited timestamps. "
        "Return ONLY JSON with keys source_sha256 and observations. Each observation has "
        "step_id, status (observed or unknown), reason, evidence_seconds (a list; empty allowed for unknown), "
        "and uncertainty (a string). Echo this source_sha256: " + source_hash + ". "
        "Samples are discrete, not uninterrupted motion. Given reference:\n" +
        json.dumps(reference, ensure_ascii=False)
    )
    request = image_sample_request(prompt, times)
    if hashlib.sha256(VIDEO.read_bytes()).hexdigest() != source_hash:
        raise ToolError("Source changed while constructing the sampling request; retry.")
    return request


def build_reference_verification(reviewer: str, reference: dict,
                                 observations: list[ReferenceObservation],
                                 reviewed_seconds: list[float], method: str) -> dict:
    duration=video_info()["duration_seconds"]
    if not reviewer.strip(): raise ToolError("Identify the host that inspected the images.")
    if not reviewed_seconds or any(not math.isfinite(t) or not 0<=t<duration for t in reviewed_seconds):
        raise ToolError("Reviewed sample times must be finite and inside this video.")
    given=validate_reference(reference)
    expected=[s.get("id") for s in given]
    actual=[s.step_id for s in observations]
    if not expected or any(not isinstance(i,str) or not i for i in expected) or len(set(expected))!=len(expected):
        raise ToolError("Reference must contain unique nonempty step IDs.")
    if sorted(expected)!=sorted(actual): raise ToolError("Require exactly one observation per given step.")
    lookup={s.step_id:s for s in observations}
    states=[]
    for index,step in enumerate(given,1):
        observed=lookup[step["id"]]
        if observed.status=="observed" and not observed.evidence_seconds:
            raise ToolError("Observed steps require cited reviewed images.")
        if any(not math.isfinite(t) or t not in reviewed_seconds for t in observed.evidence_seconds):
            raise ToolError("Evidence must reference a reviewed source frame.")
        states.append({**observed.model_dump(),"index":index,"label":step["label"],
                       "evidence_seconds":sorted(set(observed.evidence_seconds))})
    report={"title":reference["title"],"reference":reference,"steps":states,**compare_order(states),
        "reviewer":reviewer,"method":method,
        "expected_procedure_supplied":True,"source_sha256":hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
        "duration_seconds":duration,"sampled_seconds":sorted(set(reviewed_seconds)),
        "scope_note":"Visible sample evidence only. Not proof of uninterrupted execution, hidden actions, or completeness outside reviewed images."}
    return report


def write_reference_verification(report: dict, previous: dict | None = None) -> dict:
    reversed_states=[{**s,"index":i} for i,s in enumerate(report["steps"][::-1],1)]
    reverse={**report,"reference":{**report["reference"],"steps":report["reference"]["steps"][::-1]},"steps":reversed_states,
        **compare_order(reversed_states),
        "control_kind":"Same recorded observations compared to reversed reference; deterministic order control, no new vision inference."}
    REFERENCE_REVIEW.parent.mkdir(parents=True,exist_ok=True)
    if previous is not None:
        REFERENCE_REVIEW.with_name("before-verification.json").write_text(
            json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    REFERENCE_REVIEW.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    REFERENCE_REVIEW.with_name("reverse-verification.json").write_text(json.dumps(reverse,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def save_reference_verification(reviewer: str, reference: dict,
                                observations: list[ReferenceObservation],
                                reviewed_seconds: list[float], method: str) -> dict:
    return write_reference_verification(build_reference_verification(
        reviewer, reference, observations, reviewed_seconds, method))


def prior_observations(previous: dict) -> list[ReferenceObservation]:
    """Validate the supplied report before selecting a follow-up or changing output."""
    if previous.get("source_sha256") != hashlib.sha256(VIDEO.read_bytes()).hexdigest():
        raise ToolError("Prior review refers to a different source video.")
    if previous.get("expected_procedure_supplied") is not True:
        raise ToolError("Require a given-reference verification report.")
    try:
        observations = [ReferenceObservation.model_validate({k: s[k] for k in
            ("step_id", "status", "reason", "evidence_seconds", "uncertainty")})
            for s in previous["steps"]]
        derived = build_reference_verification(previous["reviewer"], previous["reference"],
            observations, previous["sampled_seconds"], previous["method"])
    except (KeyError, TypeError, ValueError) as error:
        raise ToolError(f"Invalid prior report: {error}") from error
    if (previous.get("steps") != derived["steps"] or
            previous.get("order_status") != derived["order_status"] or
            previous.get("transitions") != derived["transitions"] or
            previous.get("duration_seconds") != derived["duration_seconds"]):
        raise ToolError("Prior report does not match its reference, evidence, or source duration.")
    return observations


class RefinementBudgetError(ToolError):
    """The requested interval cannot fit all required images within the budget."""


class NoNewSamplesError(ToolError):
    """The proposed follow-up contains no source timestamps beyond the prior review."""


def refinement_plan(previous: dict, sample_interval_seconds: float, max_frames: int) -> dict:
    observations = prior_observations(previous)
    if not math.isfinite(sample_interval_seconds) or sample_interval_seconds <= 0:
        raise ToolError("Refinement interval must be finite and positive.")
    if not 2 <= max_frames <= 96:
        raise ToolError("Refinement frame budget must be between 2 and 96.")
    duration = previous["duration_seconds"]
    old_times = set(previous["sampled_seconds"])
    windows, times = [], set()
    for index, observation in enumerate(observations):
        if observation.status != "unknown":
            continue
        before = next((s for s in reversed(observations[:index]) if s.status == "observed"), None)
        after = next((s for s in observations[index + 1:] if s.status == "observed"), None)
        start = max(before.evidence_seconds) if before else 0.0
        end = min(after.evidence_seconds) if after else max(0, duration - 0.1)
        if start >= end:
            start, end = 0.0, max(0, duration - 0.1)
        count = math.ceil((end - start) / sample_interval_seconds)
        # Bound construction as well as the eventual image request.
        if count > 10000:
            raise RefinementBudgetError("Refinement would exceed the frame budget; increase the interval.")
        candidates = {round(start + i * sample_interval_seconds, 6) for i in range(count + 1)
                      if start + i * sample_interval_seconds <= end}
        candidates -= old_times
        context = {start, end} | {t for t in observation.evidence_seconds if start <= t <= end}
        times.update(candidates | context)
        windows.append({"step_id": observation.step_id, "start_seconds": start, "end_seconds": end})
    if not windows:
        raise ToolError("No unknown steps to refine.")
    if len(times) > max_frames:
        raise RefinementBudgetError("Refinement exceeds max_frames; increase the interval or frame budget.")
    if not times - old_times:
        raise NoNewSamplesError("No new samples at this interval; choose a finer interval.")
    return {"target_step_ids": [w["step_id"] for w in windows], "windows": windows,
            "sampled_seconds": sorted(times), "added_seconds": sorted(times - old_times),
            "selection_note": "Search windows use adjacent observed steps in the given reference as hints. They do not prove absence elsewhere or exclude out-of-order actions outside these windows."}


def fit_refinement_budget(previous: dict, sample_interval_seconds: float, max_frames: int) -> dict:
    """Double spacing before requesting vision; never silently drop context images."""
    attempts = []
    interval = sample_interval_seconds
    for _ in range(16):
        try:
            plan = refinement_plan(previous, interval, max_frames)
        except RefinementBudgetError:
            attempts.append({"interval_seconds": interval, "status": "over_budget"})
            interval *= 2
        except NoNewSamplesError:
            attempts.append({"interval_seconds": interval, "status": "no_new_samples"})
            return {"plan": None, "chosen_interval_seconds": None, "attempts": attempts,
                    "stop_reason": "no_new_samples"}
        else:
            attempts.append({"interval_seconds": interval, "status": "fits",
                             "frames": len(plan["sampled_seconds"])})
            return {"plan": plan, "chosen_interval_seconds": interval, "attempts": attempts,
                    "stop_reason": None}
    return {"plan": None, "chosen_interval_seconds": None, "attempts": attempts,
            "stop_reason": "refinement_budget_exhausted"}


def refinement_request(previous: dict, sample_interval_seconds: float, max_frames: int) -> Sample:
    plan = refinement_plan(previous, sample_interval_seconds, max_frames)
    target = {**previous["reference"], "steps": [s for s in previous["reference"]["steps"]
                                               if s["id"] in plan["target_step_ids"]]}
    prompt = (
        "Review only these previously UNKNOWN steps against the supplied follow-up source images. "
        "Inspect the images afresh; the reference and search window are not evidence of an action. "
        "Use observed only with visible supporting evidence; otherwise keep unknown. "
        "Return exactly one observation per supplied step ID. Cite only exact timestamps in THESE images, "
        "not other images or previous reviews. Do not infer hidden motion or assign confidence. "
        "Do not calculate order. Return ONLY JSON with source_sha256 and observations. "
        "Each observation has step_id, status (observed or unknown), reason, evidence_seconds (list; "
        "may be empty for unknown), and uncertainty (string). Echo source_sha256: " +
        previous["source_sha256"] + ". Given target reference:\n" + json.dumps(target, ensure_ascii=False) +
        "\nSampling scope: " + plan["selection_note"]
    )
    request = image_sample_request(prompt, plan["sampled_seconds"])
    if hashlib.sha256(VIDEO.read_bytes()).hexdigest() != previous["source_sha256"]:
        raise ToolError("Source changed while constructing the refinement request; retry.")
    return request


def build_refinement_result(previous: dict, sample_interval_seconds: float, max_frames: int,
                            completion: CreateMessageResult) -> dict:
    plan = refinement_plan(previous, sample_interval_seconds, max_frames)
    if completion is None or completion.content.type != "text":
        raise ToolError("The vision host must return a JSON text response.")
    try:
        answer = ReferenceCompletion.model_validate_json(completion.content.text)
    except ValueError as error:
        raise ToolError(f"Invalid refinement JSON: {error}") from error
    if answer.source_sha256 != previous["source_sha256"]:
        raise ToolError("Refinement response source hash does not match the prior video.")
    ids = [s.step_id for s in answer.observations]
    if sorted(ids) != sorted(plan["target_step_ids"]):
        raise ToolError("Require exactly one response per unknown target step; cannot modify observed steps.")
    if any(t not in plan["sampled_seconds"] for s in answer.observations for t in s.evidence_seconds):
        raise ToolError("Refinement evidence must cite an image supplied in this follow-up.")
    replacements = {s.step_id: s for s in answer.observations}
    merged = [replacements.get(s.step_id, s) for s in prior_observations(previous)]
    report = build_reference_verification(previous["reviewer"], previous["reference"], merged,
        sorted(set(previous["sampled_seconds"]) | set(plan["sampled_seconds"])),
        "MCP sampling refinement: prior observed judgments retained; host visually reviewed unknown targets using follow-up source images")
    report["refinement"] = {**plan, "reviewer": completion.model,
        "prior_order_status": previous["order_status"],
        "prior_report_sha256": hashlib.sha256(json.dumps(previous, sort_keys=True,
            ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()}
    return report


@mcp.tool()
def refine_reference_flow(previous: dict, sample_interval_seconds: float = 0.25, max_frames: int = 24,
                          completion: Annotated[CreateMessageResult, Resolve(refinement_request)] = None) -> dict:
    """Resample unknown steps and preserve prior confirmed judgments; save before/after.

    Search gaps are hints, not absence or order proof. Requires host vision sampling.
    """
    return write_reference_verification(build_refinement_result(
        previous, sample_interval_seconds, max_frames, completion), previous)


def build_verification_result(reference: dict, sample_interval_seconds: float,
                               completion: CreateMessageResult) -> dict:
    if completion is None or completion.content.type != "text":
        raise ToolError("The vision host must return a JSON text response.")
    try:
        answer = ReferenceCompletion.model_validate_json(completion.content.text)
    except ValueError as error:
        raise ToolError(f"Invalid verification JSON: {error}") from error
    if answer.source_sha256 != hashlib.sha256(VIDEO.read_bytes()).hexdigest():
        raise ToolError("Vision response source hash does not match the current video.")
    return build_reference_verification(completion.model, reference, answer.observations,
        sample_times(sample_interval_seconds),
        "MCP sampling: host vision review of supplied reference and timestamped source-frame contact sheets")


@mcp.tool()
def verify_reference_flow(reference: dict, sample_interval_seconds: float = 0.75,
                          completion: Annotated[CreateMessageResult, Resolve(reference_request)] = None) -> dict:
    """Verify a given flow through host vision sampling and derive sampled order.

    Saves validated observations and a reversed-reference control. Unknown remains unknown.
    """
    return write_reference_verification(build_verification_result(
        reference, sample_interval_seconds, completion))


def auto_initial_request(reference: dict, sample_interval_seconds: float,
                         refinement_interval_seconds: float, max_frames: int) -> Sample:
    if not math.isfinite(refinement_interval_seconds) or refinement_interval_seconds <= 0:
        raise ToolError("Refinement interval must be finite and positive.")
    if not 2 <= max_frames <= 96:
        raise ToolError("Refinement frame budget must be between 2 and 96.")
    return reference_request(reference, sample_interval_seconds)


def auto_initial_result(reference: dict, sample_interval_seconds: float,
                        completion: Annotated[CreateMessageResult, Resolve(auto_initial_request)]) -> dict:
    return build_verification_result(reference, sample_interval_seconds, completion)


def auto_interval_selection(refinement_interval_seconds: float, max_frames: int,
                            initial: Annotated[dict, Resolve(auto_initial_result)]) -> dict:
    if not any(s["status"] == "unknown" for s in initial["steps"]):
        return {"plan": None, "chosen_interval_seconds": None, "attempts": [],
                "stop_reason": "no_unknown_steps"}
    return fit_refinement_budget(initial, refinement_interval_seconds, max_frames)


def auto_followup_request(max_frames: int,
                          initial: Annotated[dict, Resolve(auto_initial_result)],
                          selection: Annotated[dict, Resolve(auto_interval_selection)]) -> Sample | None:
    if selection["plan"] is None:
        return None
    return refinement_request(initial, selection["chosen_interval_seconds"], max_frames)


@mcp.tool()
def verify_reference_flow_auto(reference: dict, sample_interval_seconds: float = 0.75,
                                refinement_interval_seconds: float = 0.25, max_frames: int = 24,
                                initial: Annotated[dict, Resolve(auto_initial_result)] = None,
                                selection: Annotated[dict, Resolve(auto_interval_selection)] = None,
                                completion: Annotated[CreateMessageResult | None, Resolve(auto_followup_request)] = None) -> dict:
    """One call: initial host vision, budget-fitted follow-up for unknowns, then stop.

    At most two sampling requests through MCP dependency resolution. Invalid
    responses raise errors without replacing saved results. Unknowns stay unknown;
    sampled order is derived from evidence, never forced to match the reference.
    """
    report, count = initial, 1
    if selection["plan"] is not None:
        report = build_refinement_result(initial, selection["chosen_interval_seconds"], max_frames, completion)
        count = 2
        stop_reason = "unknown_after_followup" if any(s["status"] == "unknown" for s in report["steps"]) else "no_unknown_steps"
    else:
        stop_reason = selection["stop_reason"]
    # Avoid changing the initial snapshot when the follow-up was skipped.
    report = {**report, "workflow": {"sampling_requests": count, "stop_reason": stop_reason,
        "unknown_step_ids": [s["step_id"] for s in report["steps"] if s["status"] == "unknown"],
        "requested_refinement_interval_seconds": refinement_interval_seconds,
        "max_frames": max_frames, "interval_selection": selection,
        "policy": "At most one follow-up. Double interval to fit the complete requested image set; preserve unknowns and prior observed judgments."}}
    write_reference_verification(report, initial if count == 2 else None)
    REFERENCE_REVIEW.with_name("initial-verification.json").write_text(
        json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


@mcp.tool()
def record_reference_verification(reviewer: str, reference: dict,
                                  observations: list[ReferenceObservation],
                                  reviewed_seconds: list[float]) -> dict:
    """Record the host's actual read_frame review of a GIVEN reference, without confidence scores.

    Trusts the host's attestation of inspected images; performs no vision inference.
    Validates sample membership and derives order, including a reversed control.
    """
    return save_reference_verification(reviewer, reference, observations, reviewed_seconds,
        "Host-attested visual review of actual MCP read_frame images; recorded review, not an inference API call.")


@mcp.tool()
def check_flow() -> dict:
    """Compare the saved visual review's timestamps with the independently defined flow.

    Missing evidence stays unknown; reversed confirmations are violations. Saves an
    order-review.json beside the configured review file.
    """
    flow = json.loads((ROOT / "examples" / "handwashing-flow.json").read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    if review["source_sha256"] != hashlib.sha256(VIDEO.read_bytes()).hexdigest():
        raise ToolError("The saved review refers to a different video.")
    result = compare_flow(flow, review)
    REVIEW.with_name("order-review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


@mcp.tool()
def record_review(reviewer: str, observations: list[Observation]) -> dict:
    """Save the host's actual visual observations, evidence times and source hash."""
    instructions = steps()
    if not reviewer.strip():
        raise ToolError("Reviewer must identify the host that inspected the images.")
    indices = [observation.index for observation in observations]
    if sorted(indices) != list(range(1, len(instructions) + 1)):
        raise ToolError("Provide exactly one observation for each procedure step.")
    duration = video_info()["duration_seconds"]
    for observation in observations:
        if any(not math.isfinite(t) or not 0 <= t < duration for t in observation.evidence_seconds):
            raise ToolError("Evidence timestamps must refer to frames inside the video.")
    report = {
        "reviewer": reviewer,
        "method": "Host vision review of extracted video frames; recorded results, not live inference",
        "source_sha256": hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
        "procedure": PROCEDURE.name,
        "duration_seconds": duration,
        "confidence_note": "Subjective model estimates, not calibrated probabilities",
        "steps": [{**observation.model_dump(), "text": instructions[observation.index - 1]}
                  for observation in sorted(observations, key=lambda item: item.index)],
    }
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"saved": str(REVIEW), "steps": len(observations), "source_sha256": report["source_sha256"]}


if __name__ == "__main__":
    mcp.run(transport="stdio")
