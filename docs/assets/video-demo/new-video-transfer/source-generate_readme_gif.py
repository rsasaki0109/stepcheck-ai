"""Replay chronological source frames, expected flow, and computed order checks.

Requires Pillow and FFmpeg. Evidence boxes are Codex annotations on reviewed frames;
no attention map, saliency values, tracking, or inference is synthesized here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont
from check_video_flow import check_flow

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
WHITE, MUTED, TEAL = "#edf3fc", "#9aaec8", "#5eead4"
AMBER, RED, BORDER = "#fcd678", "#fda4af", "#27364c"
FPS = 5
OUTPUT_SIZE = (960, 1029)
CANVAS_SIZE = (1120, 1200)
TILE_SIZE = (480, 360)


def font(size, bold=False):
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" /
        ("segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") /
        ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental") /
        ("Arial Bold.ttf" if bold else "Arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("Install Segoe UI, DejaVu Sans, or Arial to render the GIF.")


FONTS = {key: font(*args) for key, args in {
    "title": (30, True), "heading": (20, True), "body": (16,),
    "small": (13,), "label": (14, True),
}.items()}


def text(draw, xy, value, style="body", color=WHITE):
    draw.text(xy, value, font=FONTS[style], fill=color)


def box(draw, bounds, fill="#121d30", outline=BORDER, radius=12):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline)


def validate_regions(regions, report):
    if regions["source_sha256"] != report["source_sha256"]:
        raise ValueError("Evidence regions refer to a different reviewed video.")
    if len(regions["panels"]) != 4:
        raise ValueError("The four-panel layout requires exactly four stages.")
    known_steps = {step["index"] for step in report["steps"] if step["status"] == "completed"}
    previous_end = -1
    for panel in regions["panels"]:
        start, end = panel["start_seconds"], panel["end_seconds"]
        if not (previous_end < start <= end < report["duration_seconds"]):
            raise ValueError("Stage boundaries must follow source time and lie inside the video.")
        previous_end = end
        if not panel["steps"] or not set(panel["steps"]) <= known_steps:
            raise ValueError("Only observed steps can have an evidence box.")
        keys = panel["keyframes"]
        times = [key["timestamp_seconds"] for key in keys]
        if not keys or times != sorted(set(times)) or any(not start <= t <= end for t in times):
            raise ValueError("Region keyframes must be ordered, unique, and inside their stage.")
        for key in keys:
            bounds = key["bbox"]
            if len(bounds) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in bounds):
                raise ValueError("Evidence boxes must have four finite normalized coordinates.")
            if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                raise ValueError("Evidence boxes must have positive width and height.")


def region_at(panel, timestamp):
    """Show a box only on its reviewed source frame; never interpolate or track it."""
    for key in panel["keyframes"]:
        if abs(key["timestamp_seconds"] - timestamp) < 1e-5 and key.get("visible", True):
            return key["bbox"], f"Codex annotation @{timestamp:.1f}s"
    return None, ""


def evidence_overlay(frame, bounds, label):
    image = frame.convert("RGB").copy()
    if bounds is None:
        return image
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = [value * scale for value, scale in zip(bounds, (*image.size, *image.size))]
    for x, sx in [(left, 1), (right, -1)]:
        for y, sy in [(top, 1), (bottom, -1)]:
            draw.line((x, y + sy * 15, x, y, x + sx * 15, y), fill=TEAL, width=2)
    width = int(draw.textlength(label, font=FONTS["small"])) + 20
    box(draw, (10, 10, 10 + width, 36), "#111a2e", TEAL, 6)
    text(draw, (20, 15), label, "small", TEAL)
    return image


def render(source_time, cache, report, regions, flow):
    image = Image.new("RGB", CANVAS_SIZE, "#0b1120")
    draw = ImageDraw.Draw(image)
    state = check_flow(flow, report, through_seconds=source_time)
    text(draw, (32, 16), "StepCheck AI · flow verification", "title")
    text(draw, (33, 57), "Chronological video + observed actions + computed sequence checks", color=MUTED)
    text(draw, (843, 27), f"SOURCE TIME  {source_time:04.1f}s", "label", TEAL)
    text(draw, (33, 87), "EXPECTED FLOW", "small", MUTED)
    for i, step in enumerate(state["steps"]):
        x, y = 32 + i * 178, 109
        color = TEAL if step["status"] == "observed" else AMBER if step["status"] == "unknown" else RED if step["status"] == "not_done" else MUTED
        box(draw, (x, y, x + 155, y + 64), "#142639" if step["status"] == "observed" else "#121d30", color)
        text(draw, (x + 12, y + 9), f"{step['index']}  {step['label']}", "label", color)
        caption = f"seen @{step['confirmed_seconds']:.1f}s" if step["status"] == "observed" else "not visible" if step["status"] == "unknown" else "waiting for evidence"
        text(draw, (x + 12, y + 37), caption, "small", MUTED)
        if i < len(state["transitions"]):
            edge = state["transitions"][i]
            edge_color = TEAL if edge["status"] == "consistent" else RED if edge["status"] == "violated" else AMBER if edge["status"] == "unknown" else BORDER
            draw.line((x + 159, y + 32, x + 173, y + 32), fill=edge_color, width=2)
            draw.line((x + 168, y + 27, x + 173, y + 32, x + 168, y + 37), fill=edge_color, width=2)
    for i, panel in enumerate(regions["panels"]):
        x, y = 32 + (i % 2) * 540, 199 + (i // 2) * 462
        started = source_time >= panel["start_seconds"]
        finished = source_time > panel["end_seconds"] or (i == 3 and source_time >= panel["end_seconds"])
        confirmed_time = max(max(step["evidence_seconds"]) for step in report["steps"] if step["index"] in panel["steps"])
        panel_time = confirmed_time if finished else source_time
        active = started and not finished
        box(draw, (x, y, x + 516, y + 444), outline=TEAL if active else BORDER)
        text(draw, (x + 18, y + 13), f"0{i + 1}  {panel['title']}", "heading", WHITE if started else MUTED)
        text(draw, (x + 391, y + 19), f"@{panel_time:04.1f}s" if started else "PENDING", "label", TEAL if started else MUTED)
        if started:
            bounds, label = region_at(panel, panel_time)
            image.paste(evidence_overlay(cache[round(panel_time, 3)], bounds, label), (x + 18, y + 49))
            caption = "PLAYING · source chronology" if active else f"REVIEWED EVIDENCE SNAPSHOT @{panel_time:.1f}s"
        else:
            box(draw, (x + 18, y + 49, x + 498, y + 409), "#0e1728", BORDER, 4)
            text(draw, (x + 109, y + 196), "Waiting for this stage", "heading", MUTED)
            text(draw, (x + 116, y + 231), "Future frames stay hidden.", "small", MUTED)
            caption = f"Expected after stage {i}" if i else "Waiting for evidence"
        text(draw, (x + 18, y + 420), caption, "small", MUTED)

    box(draw, (32, 1121, 1088, 1170), "#142639")
    status = state["observed_order_status"]
    color = TEAL if status == "consistent" else RED if status == "violated" else MUTED
    actual = " → ".join(str(index) for index in state["observed_step_order"]) or "none yet"
    text(draw, (48, 1130), f"Observed order: {actual}  ·  {status.upper()}", "label", color)
    if state["overall_status"] == "unknown":
        detail = "Full flow: UNKNOWN · step 1 (wetting) has no visible evidence."
    elif state["overall_status"] == "violated":
        detail = "Full flow: ORDER VIOLATION · recorded timestamps contradict the expected order."
    elif state["overall_status"] == "verified":
        detail = "Full flow: VERIFIED from recorded confirmation timestamps."
    else:
        detail = "Full flow: pending · comparing confirmation timestamps as evidence appears."
    text(draw, (48, 1151), detail, "small", AMBER if state["overall_status"] == "unknown" else MUTED)
    text(draw, (33, 1180), "Recorded Codex frame review · boxes are annotations · order checks use sampled evidence timestamps", "small", MUTED)
    return image


def main():
    video = ASSETS / "source.webm"
    report = json.loads((ASSETS / "review.json").read_text(encoding="utf-8"))
    if hashlib.sha256(video.read_bytes()).hexdigest() != report["source_sha256"]:
        raise ValueError("The video differs from the reviewed source; review it again.")
    regions = json.loads((ASSETS / "regions.json").read_text(encoding="utf-8"))
    flow = json.loads((ROOT / "examples" / "handwashing-flow.json").read_text(encoding="utf-8"))
    validate_regions(regions, report)
    order = check_flow(flow, report)
    (ASSETS / "order-review.json").write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
    end = regions["panels"][-1]["end_seconds"]
    timeline = sorted({round(i / FPS, 3) for i in range(int(end * FPS) + 1)} |
                      {key["timestamp_seconds"] for panel in regions["panels"] for key in panel["keyframes"]} |
                      {panel["end_seconds"] for panel in regions["panels"]})
    with tempfile.TemporaryDirectory(prefix="stepcheck-video-") as directory:
        pattern = str(Path(directory) / "%04d.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
                        "-vf", f"fps={FPS}", pattern], check=True, timeout=30)
        cache = {}
        for i, path in enumerate(sorted(Path(directory).glob("*.png"))):
            with Image.open(path) as frame:
                cache[round(i / FPS, 3)] = frame.convert("RGB").resize(TILE_SIZE)
        exact_times = {key["timestamp_seconds"] for panel in regions["panels"] for key in panel["keyframes"]}
        exact_times |= {panel["end_seconds"] for panel in regions["panels"]}
        exact_times |= set(timeline) - set(cache)
        for timestamp in sorted(exact_times):
            path = Path(directory) / "exact.png"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(timestamp),
                            "-i", str(video), "-frames:v", "1", str(path)], check=True, timeout=30)
            with Image.open(path) as frame:
                cache[timestamp] = frame.convert("RGB").resize(TILE_SIZE)
        frames = [render(t, cache, report, regions, flow).resize(OUTPUT_SIZE, Image.Resampling.LANCZOS) for t in timeline]
    palette_sheet = Image.new("RGB", (OUTPUT_SIZE[0], OUTPUT_SIZE[1] * 8))
    for i in range(8):
        palette_sheet.paste(frames[int(i * (len(frames) - 1) / 7)], (0, i * OUTPUT_SIZE[1]))
    palette = palette_sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [max(10, round((b - a) * 100) * 10) for a, b in zip(timeline, timeline[1:])] + [3200]
    target = ROOT / "docs" / "assets" / "demo.gif"
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f"Created {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
