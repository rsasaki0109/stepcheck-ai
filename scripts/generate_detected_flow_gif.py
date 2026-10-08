"""Replay one source video with recorded VLM flow detection.

Four panels are equal source-time quarters, independent of the detected action names.
No inferred attention, boxes, action boundaries, or live model calls are rendered.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont
from generate_readme_gif import ROOT, box, text, WHITE, MUTED, TEAL, AMBER, FONTS

ASSETS = ROOT / "docs" / "assets" / "video-demo"
FPS = 5


def seen_actions(report, timestamp):
    return [action for action in report["actions"] if action["first_seen_seconds"] <= timestamp]


def render(timestamp, cache, report):
    rows = max(1, math.ceil(len(report["actions"]) / 4))
    reference = report.get("_audit", {}).get("reference_flow")
    action_top = 180 if reference else 144
    baseline_top = action_top + rows * 110
    video_top = baseline_top + (100 if reference else 0)
    canvas = Image.new("RGB", (1120, video_top + (860 if reference else 832)), "#0b1120")
    draw = ImageDraw.Draw(canvas)
    text(draw, (32, 24), "StepCheck AI  /  One video -> detected flow", "title")
    method = ("GPU -> " + report["model"].split("/")[-1]) if report["provider"] == "qwen-local" else "MCP frames -> Codex vision"
    if report.get("_audit", {}).get("run", {}).get("framewise"):
        method += " / frame observations"
    text(draw, (32, 70), method + " -> actions + evidence times", color=MUTED)
    text(draw, (32, 103), "Model output replay  |  Inspect the source to verify cited evidence", "label", AMBER)
    if reference:
        text(draw, (32, 132), "Source-review baseline: " + reference["sequence"], "small", MUTED)
        text(draw, (32, 151), "Baseline was not supplied to the model. Cards below are its unmodified predictions.", "small", MUTED)
    visible = seen_actions(report, timestamp)
    # Only reveal labels once supporting evidence has appeared in source time.
    for index in range(max(1, len(report["actions"]))):
        x, y = 32 + (index % 4) * 268, action_top + (index // 4) * 110
        action = report["actions"][index] if report["actions"] else None
        observed = action is not None and action in visible
        review = next((item for item in report.get("_audit", {}).get("actions", []) if action and item["id"] == action["id"]), None)
        mismatch = observed and review is not None and review["status"] != "supported"
        box(draw, (x, y, x + 252, y + 104), outline=AMBER if mismatch else TEAL if observed else "#27364c")
        text(draw, (x + 12, y + 9), f"{index + 1:02d}" if action else "--", "label", TEAL if observed else MUTED)
        if observed:
            lines = []
            line = ""
            for character in action["label"]:
                if line and draw.textlength(line + character, font=FONTS["body"]) > 196:
                    lines.append(line.strip())
                    line = ""
                line += character
            lines.append(line.strip())
            if len(lines) > 2:
                lines[1] = lines[1][:-1] + "…"
            lines = lines[:2]
            for line_index, line in enumerate(lines):
                text(draw, (x + 42, y + 8 + line_index * 20), line, "body")
            times = [t for t in action["evidence_seconds"] if t <= timestamp]
            text(draw, (x + 12, y + 62), f"Evidence cited: {times[0]:.2f} - {times[-1]:.2f}s", "small", TEAL)
            if review:
                text(draw, (x + 12, y + 79), "Review: " + review["status"].replace("_", " "), "small", AMBER if mismatch else TEAL)
        else:
            text(draw, (x + 42, y + 24), "Awaiting source evidence", "small", MUTED)
        if index < len(report["actions"]) - 1 and index % 4 < 3:
            uncertain = report["transitions"][index]["status"] == "ambiguous"
            text(draw, (x + 255, y + 37), "?" if uncertain else ">", "small", AMBER if uncertain else MUTED)
    if reference:
        complete = timestamp >= max(report["sampled_seconds"])
        order_status = reference["order_status"] if complete else "pending"
        text(draw, (32, baseline_top + 2), "Independent 7-step comparison  /  Full flow + order: " + order_status, "small", AMBER)
        for index, step in enumerate(reference["steps"]):
            x, y = 32 + index * 151, baseline_top + 26
            status = step["status"] if complete else "pending"
            color = TEAL if status == "supported" else AMBER if complete else MUTED
            box(draw, (x, y, x + 141, y + 62), outline=color)
            label = step["label"].replace("Hold door handle", "Door handle").replace("Lower towel into bin", "Lower into bin")
            text(draw, (x + 9, y + 9), f"{step['index']}. {label}", "small", WHITE)
            text(draw, (x + 9, y + 33), status.replace("_", " "), "small", color)
    quarter = report["duration_seconds"] / 4
    for index in range(4):
        x, y = 32 + (index % 2) * 548, video_top + (index // 2) * 374
        start, finish = index * quarter, (index + 1) * quarter
        box(draw, (x, y, x + 528, y + 356))
        text(draw, (x + 16, y + 12), f"Part {index + 1}  /  {start:.1f}-{finish:.1f}s", "heading")
        if timestamp >= start:
            candidates = [t for t in cache if start <= t < finish and t <= timestamp]
            if candidates:
                source_time = max(candidates)
                frame = cache[source_time].resize((416, 312), Image.Resampling.LANCZOS)
                canvas.paste(frame, (x + 56, y + 42))
                # Timestamp tag is outside the source pixels.
                text(draw, (x + 420, y + 17), f"@{source_time:g}s", "small", TEAL)
        else:
            text(draw, (x + 105, y + 170), "Waiting for this part of the video", color=MUTED)
    footer = video_top + 754
    text(draw, (32, footer), f"Source {timestamp:.2f}/{report['duration_seconds']:.2f}s  |  {len(visible)} reported actions", "label", TEAL)
    text(draw, (32, footer + 27), "Times mark reviewed samples, not action boundaries. Short actions may be missed.", "small", MUTED)
    note = "Amber cards: review found incomplete or incorrect evidence. Model output is unchanged." if report.get("_audit") else "No attention map. '?' marks ambiguous order. Model evidence can be wrong."
    text(draw, (32, footer + 49), note, "small", AMBER)
    if reference:
        outcome = reference["summary"] if timestamp >= max(report["sampled_seconds"]) else "Review comparison: pending until all source quarters have played."
        text(draw, (32, footer + 72), outcome, "small", AMBER)
    return canvas.resize((960, round(canvas.height * 960 / 1120)), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ASSETS / "detected-flow.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/detected-flow.gif")
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if args.audit:
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        report_digest = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if audit["source_sha256"] != report["source_sha256"] or audit["report_sha256"] != report_digest:
            raise ValueError("Review differs from the replayed model report or video.")
        report["_audit"] = audit
    if any(ord(character) > 127 for action in report["actions"] for character in action["label"]):
        candidates = [Path("C:/Windows/Fonts/meiryo.ttc"),
                      Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
        cjk = next((path for path in candidates if path.exists()), None)
        if cjk is None:
            raise RuntimeError("Install Meiryo or Noto Sans CJK to render model labels.")
        FONTS.update({key: ImageFont.truetype(str(cjk), font.size) for key, font in FONTS.items()})
    video = ASSETS / "source.webm"
    if hashlib.sha256(video.read_bytes()).hexdigest() != report["source_sha256"]:
        raise ValueError("Video differs from the detected source.")
    end = max(report["sampled_seconds"])
    timeline = sorted(set([round(i / FPS, 6) for i in range(math.floor(end * FPS) + 1)] + report["sampled_seconds"]))
    with tempfile.TemporaryDirectory() as directory:
        cache = {}
        for timestamp in timeline:
            path = Path(directory) / "frame.png"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(timestamp),
                            "-i", str(video), "-frames:v", "1", str(path)], check=True, timeout=30)
            with Image.open(path) as frame:
                cache[timestamp] = frame.convert("RGB")
        frames = [render(t, cache, report) for t in timeline]
    width, height = frames[0].size
    sheet = Image.new("RGB", (width, height * 8))
    for index in range(8):
        sheet.paste(frames[round(index * (len(frames) - 1) / 7)], (0, index * height))
    palette = sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [max(10, round((b - a) * 100) * 10) for a, b in zip(timeline, timeline[1:])] + [6500]
    target = args.output
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f"Created {target.resolve()} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
