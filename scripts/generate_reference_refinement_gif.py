"""Replay saved MCP verification, follow-up images, and the resulting sampled order.

No recognition runs during this animation. Follow-up frames use the actual saved
sampling plan; previously confirmed steps are preserved, not judged again.
"""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path

from PIL import Image

from generate_detected_flow_gif import FPS, render
from generate_readme_gif import MUTED, AMBER, TEAL, text
from PIL import ImageDraw
from verify_qwen3_video_flow import verification_replay_report, compare_order
from video_mcp import VIDEO, frame_bytes, prior_observations


def replay(report):
    frames = {"source_sha256": report["source_sha256"], "duration_seconds": report["duration_seconds"],
              "frames": [{"timestamp_seconds": t} for t in report["sampled_seconds"]]}
    result = verification_replay_report({**report, "model": "Codex host vision review",
        "provider": "codex-mcp", "input_modality": "MCP sampling source images"}, frames)
    short = ["Soap", "Lather", "Rinse", "Pull towel", "Dry", "Door handle", "Lower into bin"]
    supported = sum(s["status"] == "observed" for s in report["steps"])
    reverse = compare_order(list(reversed(report["steps"])))
    violations = sum(t["status"] == "violated" for t in reverse["transitions"])
    unknown = sum(t["status"] == "unknown" for t in reverse["transitions"])
    result["_audit"] = {"actions": [{"id": s["index"],
        "status": "supported" if s["status"] == "observed" else "unknown"} for s in report["steps"]],
        "reference_flow": {"sequence": "soap > lather > rinse > pull towel > dry > door handle > bin",
            "order_status": report["order_status"], "summary": f"{supported}/7 visible actions supported. Door opening / towel release remain unconfirmed.",
            "steps": [{"index": s["index"], "label": short[i],
                "status": "supported" if s["status"] == "observed" else "unknown"} for i, s in enumerate(report["steps"])]},
        "control_summary": "Same evidence + reversed reference: " +
            f"{violations} violations, {unknown} unknown. Not a second inference."}
    return result


def banner(frame, title, detail, color):
    canvas = Image.new("RGB", (frame.width, frame.height + 76), "#0b1120")
    canvas.paste(frame, (0, 76))
    draw = ImageDraw.Draw(canvas)
    text(draw, (27, 13), title, "heading", color)
    text(draw, (27, 44), detail, "small", MUTED)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before, after = [json.loads(p.read_text(encoding="utf-8")) for p in (args.before, args.after)]
    prior_observations(before)
    prior_observations(after)
    digest = hashlib.sha256(json.dumps(before, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()
    if after["refinement"]["prior_report_sha256"] != digest:
        raise ValueError("Refinement does not belong to the supplied before report.")
    if before["reference"] != after["reference"] or any(a != b for a, b in
            zip(before["steps"], after["steps"]) if a["status"] == "observed"):
        raise ValueError("Refinement changed the reference or a previously confirmed step.")
    if [s["step_id"] for s in before["steps"]] != ["soap", "lather", "rinse", "paper", "dry", "door", "bin"] or after["refinement"]["target_step_ids"] != ["door"]:
        raise ValueError("This demo layout requires the bundled seven-step reference and a handle follow-up.")
    if hashlib.sha256(VIDEO.read_bytes()).hexdigest() != after["source_sha256"]:
        raise ValueError("Source video differs from the recorded review.")
    end = max(before["sampled_seconds"])
    timeline = sorted(set([round(i / FPS, 6) for i in range(math.floor(end * FPS) + 1)] + before["sampled_seconds"]))
    followup = after["refinement"]["sampled_seconds"]
    cache = {t: Image.open(io.BytesIO(frame_bytes(t))).convert("RGB") for t in sorted(set(timeline + followup))}
    # Stage 1 cannot see later follow-up source samples or judgments.
    initial_cache = {t: cache[t] for t in timeline}
    first, final = replay(before), replay(after)
    images = [banner(render(t, initial_cache, first), f"PASS 1 / {len(before['sampled_seconds'])} samples / handle remains UNKNOWN",
        "Recorded MCP host review. No live inference, attention map, or confidence score.", AMBER) for t in timeline]
    durations = [max(10, round((b - a) * 100) * 10) for a, b in zip(timeline, timeline[1:])] + [2500]
    quarter_start = after["duration_seconds"] * 3 / 4
    window = after["refinement"]["windows"][0]
    added = len(after["refinement"]["added_seconds"])
    detail = f"{window['start_seconds']:g}-{window['end_seconds']:g}s from neighboring evidence; {added} new + {len(followup)-added} context samples. Judgment stays unknown here."
    for timestamp in followup:
        view = {t: f for t, f in cache.items() if t < quarter_start or t <= timestamp}
        images.append(banner(render(end, view, first), "PASS 2 / review unknown handle / source " + f"{timestamp:g}s",
            detail, AMBER))
        durations.append(550)
    evidence_time = next(iter(after["steps"][5]["evidence_seconds"]), followup[-1])
    result_cache = {t: f for t, f in cache.items() if t < quarter_start or t <= evidence_time}
    order_label = "SUPPORTED" if after["order_status"] == "supported_sample_order" else after["order_status"].upper()
    images.append(banner(render(end, result_cache, final), "RESULT / handle " + after["steps"][5]["status"].upper() + " / sampled order " + order_label,
        "Recorded follow-up judgment; first review retained. Same evidence against reversed reference is checked below.", TEAL if after["order_status"] == "supported_sample_order" else AMBER))
    durations.append(6500)
    palette_sheet = Image.new("RGB", (images[0].width, images[0].height * 8))
    for i in range(8):
        palette_sheet.paste(images[round(i * (len(images) - 1) / 7)], (0, i * images[0].height))
    palette = palette_sheet.quantize(colors=256)
    encoded = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in images]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded[0].save(args.output, save_all=True, append_images=encoded[1:], duration=durations,
                    loop=0, optimize=True, disposal=1)
    print(f"Created {args.output.resolve()} ({args.output.stat().st_size:,} bytes; {len(images)} frames)")


if __name__ == "__main__":
    main()
