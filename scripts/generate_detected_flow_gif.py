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
    video_top = 144 + rows * 110
    canvas = Image.new("RGB", (1120, video_top + 832), "#0b1120")
    draw = ImageDraw.Draw(canvas)
    text(draw, (32, 24), "StepCheck AI  /  One video -> detected flow", "title")
    method = "Colab GPU -> Qwen local VLM" if report["provider"] == "qwen-local" else "MCP frames -> Codex vision"
    text(draw, (32, 70), method + " -> actions + evidence times", color=MUTED)
    text(draw, (32, 103), "Model output replay  |  Inspect the source to verify cited evidence", "label", AMBER)
    visible = seen_actions(report, timestamp)
    # Only reveal labels once supporting evidence has appeared in source time.
    for index in range(max(1, len(report["actions"]))):
        x, y = 32 + (index % 4) * 268, 144 + (index // 4) * 110
        action = report["actions"][index] if report["actions"] else None
        observed = action is not None and action in visible
        box(draw, (x, y, x + 252, y + 94), outline=TEAL if observed else "#27364c")
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
        else:
            text(draw, (x + 42, y + 24), "Awaiting source evidence", "small", MUTED)
        if index < len(report["actions"]) - 1 and index % 4 < 3:
            uncertain = report["transitions"][index]["status"] == "ambiguous"
            text(draw, (x + 255, y + 37), "?" if uncertain else ">", "small", AMBER if uncertain else MUTED)
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
    text(draw, (32, footer + 49), "No attention map. '?' marks ambiguous order. Model evidence can be wrong.", "small", AMBER)
    return canvas.resize((960, round(canvas.height * 960 / 1120)), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ASSETS / "detected-flow.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/detected-flow.gif")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
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
    durations = [max(10, round((b - a) * 100) * 10) for a, b in zip(timeline, timeline[1:])] + [3500]
    target = args.output
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f"Created {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
