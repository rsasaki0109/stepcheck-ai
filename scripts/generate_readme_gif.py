"""Replay real footage alongside saved Codex vision observations.

Requires Pillow and FFmpeg. Run: python scripts/generate_readme_gif.py
Rendering does not run inference; review.json was produced by visual frame review.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "video-demo"
WHITE, MUTED, TEAL = "#edf3fc", "#9aaec8", "#5eead4"
PURPLE, BORDER = "#b9a4ff", "#27364c"
COLORS = {"completed": TEAL, "not_done": "#fda4af", "unknown": "#fcd678"}
LABELS = {"completed": "Observed", "not_done": "Not done", "unknown": "Not visible"}
FPS = 5
OUTPUT_SIZE = (960, 617)


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
    "title": (32, True), "heading": (19, True), "body": (16,),
    "small": (13,), "label": (14, True),
}.items()}


def text(draw, xy, value, style="body", color=WHITE):
    draw.text(xy, value, font=FONTS[style], fill=color)


def box(draw, bounds, fill="#121d30", outline=BORDER, radius=14):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline)


def wrap(draw, value, width, style="body"):
    lines = [""]
    for word in value.split():
        candidate = (lines[-1] + " " + word).strip()
        if draw.textlength(candidate, font=FONTS[style]) > width:
            lines.append(word)
        else:
            lines[-1] = candidate
    return lines


def render(frame, t, report):
    image = Image.new("RGB", (1120, 720), "#0b1120")
    draw = ImageDraw.Draw(image)
    text(draw, (32, 23), "StepCheck AI", "title")
    text(draw, (33, 68), "Video frames → Codex vision → procedure verification", color=MUTED)
    box(draw, (811, 30, 1088, 64), "#1d2840")
    text(draw, (826, 38), "RECORDED VISION REVIEW  /  MCP", "small", PURPLE)
    box(draw, (32, 111, 627, 605))
    text(draw, (49, 128), "VIDEO EVIDENCE", "label", MUTED)
    text(draw, (487, 128), f"{t:04.1f}s / 23.0s", "label", TEAL)
    image.paste(ImageOps.fit(frame, (560, 420)), (49, 164))
    box(draw, (647, 111, 1088, 605))
    text(draw, (667, 128), "Procedure checklist", "heading")
    visible = [step for step in report["steps"] if max(step["evidence_seconds"]) <= t]
    done = sum(step["status"] == "completed" for step in visible)
    text(draw, (968, 133), f"{done} / 6", "label", TEAL)
    for i, step in enumerate(report["steps"]):
        y = 170 + i * 69
        known = max(step["evidence_seconds"]) <= t
        color = COLORS[step["status"]] if known else MUTED
        box(draw, (665, y, 1070, y + 62), "#172439", BORDER, 9)
        draw.ellipse((676, y + 18, 701, y + 43), outline=color, width=2)
        if known and step["status"] == "completed":
            draw.line((682, y + 30, 687, y + 35, 695, y + 25), fill=color, width=2)
        else:
            text(draw, (683, y + 20), "?" if known else str(i + 1), "small", color)
        lines = wrap(draw, step["text"], 342, "label")
        for j, line in enumerate(lines):
            text(draw, (713, y + 5 + 17 * j), line, "label")
        caption = "Awaiting evidence"
        if known:
            caption = f"{LABELS[step['status']]} · {step['confidence']:.0%} estimate · @{max(step['evidence_seconds']):.1f}s"
        text(draw, (713, y + 41), caption, "small", color)

    # Explanations change only at timestamps actually reviewed by the host.
    observed = [step for step in visible if step["status"] == "completed"]
    current = max(observed, key=lambda step: max(step["evidence_seconds"])) if observed else None
    box(draw, (32, 621, 1088, 681), "#142639", BORDER, 12)
    if current:
        text(draw, (49, 632), f"VISION EVIDENCE  @{max(current['evidence_seconds']):.1f}s", "small", TEAL)
        text(draw, (49, 651), current["reason"], "small")
    else:
        text(draw, (49, 632), "VISION EVIDENCE", "small", TEAL)
        text(draw, (49, 651), "Reviewing the source frames against the written procedure…", "small")
    text(draw, (33, 693), "Real CDC footage · replay of Codex frame review · estimates are not calibrated probabilities", "small", MUTED)
    return image


def main():
    video = ASSETS / "source.webm"
    report = json.loads((ASSETS / "review.json").read_text(encoding="utf-8"))
    if hashlib.sha256(video.read_bytes()).hexdigest() != report["source_sha256"]:
        raise ValueError("The video differs from the reviewed source; review it again.")
    with tempfile.TemporaryDirectory(prefix="stepcheck-video-") as directory:
        pattern = str(Path(directory) / "%04d.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
                        "-vf", f"fps={FPS}", pattern], check=True, timeout=60)
        frames = []
        for i, path in enumerate(sorted(Path(directory).glob("*.png"))):
            with Image.open(path) as frame:
                frames.append(render(frame.convert("RGB"), i / FPS, report)
                              .resize(OUTPUT_SIZE, Image.Resampling.LANCZOS))
    # Derive a single palette from frames across the clip, including the UI.
    palette_sheet = Image.new("RGB", (OUTPUT_SIZE[0], OUTPUT_SIZE[1] * 8))
    for i in range(8):
        palette_sheet.paste(frames[int(i * (len(frames) - 1) / 7)], (0, i * OUTPUT_SIZE[1]))
    palette = palette_sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    durations = [200] * len(frames)
    durations[-1] = 3200  # Hold the final observations so the checklist is readable.
    target = ROOT / "docs" / "assets" / "demo.gif"
    frames[0].save(target, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    print(f"Created {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
