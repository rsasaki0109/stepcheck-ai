"""Render four video excerpts with visually annotated evidence-region overlays.

Requires Pillow and FFmpeg. Run: python scripts/generate_readme_gif.py
The heat overlay illustrates Codex's saved evidence boxes, not model attention.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
WHITE, MUTED, TEAL = "#edf3fc", "#9aaec8", "#5eead4"
PURPLE, BORDER = "#b9a4ff", "#27364c"
FPS = 5
OUTPUT_SIZE = (960, 951)
CANVAS_SIZE = (1120, 1110)
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
    "title": (32, True), "heading": (21, True), "body": (16,),
    "small": (13,), "label": (14, True),
}.items()}


def text(draw, xy, value, style="body", color=WHITE):
    draw.text(xy, value, font=FONTS[style], fill=color)


def box(draw, bounds, fill="#121d30", outline=BORDER, radius=14):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline)


def validate_regions(regions, report):
    if regions["source_sha256"] != report["source_sha256"]:
        raise ValueError("Evidence regions refer to a different reviewed video.")
    if len(regions["panels"]) != 4:
        raise ValueError("The four-panel layout requires exactly four excerpts.")
    known_steps = {step["index"] for step in report["steps"] if step["status"] == "completed"}
    for panel in regions["panels"]:
        start, end = panel["start_seconds"], panel["end_seconds"]
        if not (0 <= start < end < report["duration_seconds"]):
            raise ValueError("Excerpt boundaries must lie inside the reviewed video.")
        if not panel["steps"] or not set(panel["steps"]) <= known_steps:
            raise ValueError("Only observed steps can have an evidence highlight.")
        keys = panel["keyframes"]
        times = [key["timestamp_seconds"] for key in keys]
        if not keys or times != sorted(set(times)) or any(not start <= t <= end for t in times):
            raise ValueError("Region keyframes must be ordered, unique, and inside their excerpt.")
        for key in keys:
            bounds = key["bbox"]
            if len(bounds) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in bounds):
                raise ValueError("Evidence boxes must have four finite normalized coordinates.")
            left, top, right, bottom = bounds
            if left >= right or top >= bottom:
                raise ValueError("Evidence boxes must have positive width and height.")


def region_at(panel, timestamp):
    """Interpolate reviewed boxes for display; this does not track or infer objects."""
    keys = panel["keyframes"]
    if timestamp <= keys[0]["timestamp_seconds"]:
        return keys[0]["bbox"] if keys[0].get("visible", True) else None, keys[0]["label"]
    for left, right in zip(keys, keys[1:]):
        if timestamp <= right["timestamp_seconds"]:
            mix = (timestamp - left["timestamp_seconds"]) / (right["timestamp_seconds"] - left["timestamp_seconds"])
            bounds = [a + (b - a) * mix for a, b in zip(left["bbox"], right["bbox"])]
            chosen = left if mix < 0.5 else right
            return bounds if chosen.get("visible", True) else None, chosen["label"]
    return keys[-1]["bbox"] if keys[-1].get("visible", True) else None, keys[-1]["label"]


def evidence_overlay(frame, bounds, label):
    """Draw a warm, soft evidence cue with no simulated attention scores."""
    image = frame.convert("RGBA")
    if bounds is None:
        return image.convert("RGB")
    w, h = image.size
    left, top, right, bottom = [value * scale for value, scale in zip(bounds, (w, h, w, h))]
    center_x, center_y = (left + right) / 2, (top + bottom) / 2
    radius_x, radius_y = (right - left) / 2, (bottom - top) / 2
    # Nested blurred masks give the annotated region a heatmap-like appearance.
    for scale, color, alpha in [(1.05, (156, 84, 245), 50), (0.77, (255, 92, 52), 65), (0.43, (255, 218, 74), 70)]:
        mask = Image.new("L", image.size)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((center_x - radius_x * scale, center_y - radius_y * scale,
                      center_x + radius_x * scale, center_y + radius_y * scale), fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(max(8, min(radius_x, radius_y) * 0.22)))
        tint = Image.new("RGBA", image.size, color)
        tint.putalpha(mask)
        image = Image.alpha_composite(image, tint)
    draw = ImageDraw.Draw(image)
    # Corner marks distinguish the actual annotated box from the decorative glow.
    for x, sx in [(left, 1), (right, -1)]:
        for y, sy in [(top, 1), (bottom, -1)]:
            draw.line((x, y + sy * 15, x, y, x + sx * 15, y), fill="#fff0a1", width=2)
    label_width = int(draw.textlength(label, font=FONTS["label"])) + 22
    box(draw, (10, 10, 10 + label_width, 39), "#111a2e", "#f3b875", 7)
    text(draw, (21, 16), label, "label", "#ffdf8d")
    return image.convert("RGB")


def render(frame_sets, elapsed, report, regions):
    image = Image.new("RGB", CANVAS_SIZE, "#0b1120")
    draw = ImageDraw.Draw(image)
    text(draw, (32, 20), "StepCheck AI", "title")
    text(draw, (33, 65), "Four video excerpts · Codex vision · highlighted evidence", color=MUTED)
    box(draw, (830, 29, 1088, 63), "#1d2840")
    text(draw, (845, 38), "EVIDENCE REGION OVERLAY", "small", PURPLE)
    for i, panel in enumerate(regions["panels"]):
        x, y = 32 + (i % 2) * 540, 107 + (i // 2) * 462
        source_time = min(panel["start_seconds"] + elapsed, panel["end_seconds"])
        frame_index = min(int(elapsed * FPS), len(frame_sets[i]) - 1)
        bounds, label = region_at(panel, source_time)
        box(draw, (x, y, x + 516, y + 444))
        text(draw, (x + 18, y + 13), f"0{i + 1}  {panel['title']}", "heading")
        text(draw, (x + 397, y + 18), f"@{source_time:04.1f}s", "label", TEAL)
        image.paste(evidence_overlay(frame_sets[i][frame_index], bounds, label), (x + 18, y + 49))
        # Status refers to the recorded sequence review, not a new inference per frame.
        text(draw, (x + 18, y + 420), panel["caption"], "small", MUTED)
        draw.ellipse((x + 483, y + 422, x + 496, y + 435), fill=TEAL)

    box(draw, (32, 1029, 1088, 1065), "#142639")
    observed = sum(step["status"] == "completed" for step in report["steps"])
    text(draw, (48, 1037), f"{observed} / {len(report['steps'])} steps observed  ·  Pre-soap wetting: unknown", "label", TEAL)
    text(draw, (708, 1037), "Warm glow = annotated evidence", "small", "#ffdf8d")
    text(draw, (33, 1078), "Recorded visual review · interpolated evidence boxes · overlay is not internal model attention", "small", MUTED)
    return image


def main():
    video = ASSETS / "source.webm"
    report = json.loads((ASSETS / "review.json").read_text(encoding="utf-8"))
    if hashlib.sha256(video.read_bytes()).hexdigest() != report["source_sha256"]:
        raise ValueError("The video differs from the reviewed source; review it again.")
    regions = json.loads((ASSETS / "regions.json").read_text(encoding="utf-8"))
    validate_regions(regions, report)
    with tempfile.TemporaryDirectory(prefix="stepcheck-video-") as directory:
        frame_sets = []
        for i, panel in enumerate(regions["panels"]):
            pattern = str(Path(directory) / f"{i}-%04d.png")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(panel["start_seconds"]),
                            "-i", str(video), "-t", str(panel["end_seconds"] - panel["start_seconds"]),
                            "-vf", f"fps={FPS},scale={TILE_SIZE[0]}:{TILE_SIZE[1]}", pattern],
                           check=True, timeout=30)
            images = []
            for path in sorted(Path(directory).glob(f"{i}-*.png")):
                with Image.open(path) as frame:
                    images.append(frame.convert("RGB"))
            # An exact end frame keeps frozen video and its annotation timestamp aligned.
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(panel["end_seconds"]),
                                     "-i", str(video), "-frames:v", "1", str(Path(directory) / f"end-{i}.png")],
                                    capture_output=True, check=True, timeout=30)
            with Image.open(Path(directory) / f"end-{i}.png") as frame:
                images.append(frame.convert("RGB").resize(TILE_SIZE, Image.Resampling.LANCZOS))
            frame_sets.append(images)
        duration = max(panel["end_seconds"] - panel["start_seconds"] for panel in regions["panels"]) + 1.2
        frames = [render(frame_sets, i / FPS, report, regions).resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
                  for i in range(math.ceil(duration * FPS))]
    palette_sheet = Image.new("RGB", (OUTPUT_SIZE[0], OUTPUT_SIZE[1] * 6))
    for i in range(6):
        palette_sheet.paste(frames[int(i * (len(frames) - 1) / 5)], (0, i * OUTPUT_SIZE[1]))
    palette = palette_sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    target = ROOT / "docs" / "assets" / "demo.gif"
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=200,
                   loop=0, optimize=True, disposal=1)
    print(f"Created {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
