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

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
VIDEO = Path(os.environ.get("STEPCHECK_DEMO_VIDEO", str(ASSETS / "source.webm")))
REVIEW = Path(os.environ.get("STEPCHECK_DEMO_REVIEW", str(ASSETS / "review.json")))
DETECTED_FLOW = Path(os.environ.get("STEPCHECK_DETECTED_FLOW", str(ASSETS / "detected-flow.json")))
PROCEDURE = ROOT / "examples" / "handwashing.md"
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
