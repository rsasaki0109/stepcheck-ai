"""Local stdio MCP tools: video -> image content -> host vision review -> JSON.

The MCP server extracts frames; the connected vision-capable host judges them.
No server-side model call, mock provider, API key, or automatic verdict is involved.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field
from check_video_flow import check_flow as compare_flow

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
VIDEO = Path(os.environ.get("STEPCHECK_DEMO_VIDEO", str(ASSETS / "source.webm")))
REVIEW = Path(os.environ.get("STEPCHECK_DEMO_REVIEW", str(ASSETS / "review.json")))
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
