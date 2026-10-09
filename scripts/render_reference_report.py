"""Export recorded MCP reference judgments and their source evidence to HTML."""

import argparse
import base64
import hashlib
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

from PIL import Image

from verify_qwen3_video_flow import compare_order


def validate_report(report, source_hash):
    if report["source_sha256"] != source_hash:
        raise ValueError("Report belongs to another source video.")
    duration = report["duration_seconds"]
    samples = report["sampled_seconds"]
    if not math.isfinite(duration) or duration <= 0 or not samples or any(
            not math.isfinite(t) or not 0 <= t < duration for t in samples):
        raise ValueError("Invalid reviewed timestamps.")
    expected = report["reference"]["steps"]
    if not expected or len({s["id"] for s in expected}) != len(expected):
        raise ValueError("Invalid reference IDs.")
    if [s["step_id"] for s in report["steps"]] != [s["id"] for s in expected]:
        raise ValueError("Verdicts differ from the reference IDs/order.")
    for step, reference in zip(report["steps"], expected):
        if step["label"] != reference["label"] or step["status"] not in ("observed", "unknown"):
            raise ValueError("Invalid reference verdict.")
        if step["status"] == "observed" and not step["evidence_seconds"]:
            raise ValueError("Observed without evidence.")
        if any(t not in samples for t in step["evidence_seconds"]):
            raise ValueError("Citation was not reviewed.")
    derived = compare_order(report["steps"])
    if any(report[key] != derived[key] for key in ("transitions", "order_status")):
        raise ValueError("Saved order differs from cited evidence.")


def validate_initial(final, initial, source_hash):
    validate_report(initial, source_hash)
    if initial["reference"] != final["reference"] or not set(initial["sampled_seconds"]) <= set(final["sampled_seconds"]):
        raise ValueError("Initial and final reports differ in reference or reviewed samples.")
    if "refinement" in final:
        digest = hashlib.sha256(json.dumps(initial, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        if digest != final["refinement"]["prior_report_sha256"]:
            raise ValueError("Initial report does not match the refinement provenance.")
    for before, after in zip(initial["steps"], final["steps"]):
        if before["status"] == "observed" and before != after:
            raise ValueError("Follow-up changed a previously observed step.")


def sampling_sheets(bridge):
    sheets = []
    directories = sorted(bridge.glob("pass-*")) or [bridge]
    for directory in directories:
        request_path = directory / "sampling-request.json"
        if not request_path.exists():
            continue
        request = json.loads(request_path.read_text(encoding="utf-8"))
        for item in request["images"]:
            name = Path(item["file"])
            if name.name != str(name) or name.is_absolute():
                raise ValueError("Sampling image must be a local filename.")
            data = (directory / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("Sampling image differs from the exported MCP request.")
            sheets.append({"pass": directory.name, "file": name.name,
                "url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")})
    return sheets


def validate_bridge_report(bridge, report):
    result = json.loads((bridge / "tool-result.json").read_text(encoding="utf-8"))
    if result.get("is_error", result.get("isError", False)):
        raise ValueError("Cannot attach images from a failed MCP run.")
    recorded = [json.loads(block["text"]) for block in result["content"] if block["type"] == "text"]
    if report not in recorded:
        raise ValueError("Sampling capture and report differ in MCP result.")
    directories = sorted(bridge.glob("pass-*")) or [bridge]
    for directory in directories:
        response = json.loads((directory / "response.json").read_text(encoding="utf-8"))
        if response["source_sha256"] != report["source_sha256"]:
            raise ValueError("Sampling response belongs to another video.")


def thumbnail(video, timestamp):
    data = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(video),
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True, timeout=30).stdout
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((640, 360))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def render_report(report, video, destination, *, initial=None, bridge=None, credit="", linked_video=False):
    video_data = video.read_bytes()
    source_hash = hashlib.sha256(video_data).hexdigest()
    validate_report(report, source_hash)
    if initial is not None:
        validate_initial(report, initial, source_hash)
    if bridge:
        validate_bridge_report(bridge, report)
    sheets = sampling_sheets(bridge) if bridge else []
    frames = {str(t): thumbnail(video, t) for t in sorted(set(report["sampled_seconds"]))}
    if hashlib.sha256(video.read_bytes()).hexdigest() != source_hash:
        raise ValueError("Source video changed while exporting evidence.")
    if linked_video:
        source = quote(Path(os.path.relpath(video.resolve(), destination.parent.resolve())).as_posix(), safe="/.")
    else:
        media_type = mimetypes.guess_type(str(video))[0] or "video/mp4"
        source = f"data:{media_type};base64," + base64.b64encode(video_data).decode("ascii")
    payload = {"final": report, "initial": initial, "frames": frames,
        "sheets": sheets, "source": source, "credit": credit}
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (Path(__file__).parent / "templates/reference_report.html").read_text(encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(re.sub("__DATA__", lambda _: serialized, template), encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--bridge-dir", type=Path)
    parser.add_argument("--source-credit", default="")
    parser.add_argument("--linked-video", action="store_true", help="Link source relatively instead of embedding it")
    args = parser.parse_args()
    render_report(json.loads(args.report.read_text(encoding="utf-8")), args.video, args.output,
        initial=json.loads(args.initial.read_text(encoding="utf-8")) if args.initial else None,
        bridge=args.bridge_dir, credit=args.source_credit, linked_video=args.linked_video)
    print(f"Open {args.output.resolve()}")


if __name__ == "__main__":
    main()
