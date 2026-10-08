"""Render the README workflow illustration, using the real MockProvider.

This is an illustration, not a recording of the app. Requires Pillow:
    python -m pip install Pillow
    python scripts/generate_readme_gif.py
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "providers"))

from stepcheck_providers import ImagePayload, ProcedureStep, VerificationInput
from stepcheck_providers.mock_provider import MockProvider

WHITE, MUTED, TEAL = "#edf3fc", "#9aaec8", "#5eead4"
PURPLE, BORDER = "#b9a4ff", "#27364c"
COLORS = {"completed": TEAL, "not_done": "#fda4af", "unknown": "#fcd678"}
LABELS = {"completed": "Completed", "not_done": "Not done", "unknown": "Undetermined"}


def font(size, bold=False, mono=False):
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" /
        ("consola.ttf" if mono else "segoeuib.ttf" if bold else "segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") /
        ("DejaVuSansMono.ttf" if mono else "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental") /
        ("Courier New.ttf" if mono else "Arial Bold.ttf" if bold else "Arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError("Install Segoe UI, DejaVu Sans, or Arial to render the GIF.")


FONTS = {name: font(*args) for name, args in {
    "title": (34, True), "heading": (20, True), "body": (16,),
    "small": (13,), "label": (14, True), "mono": (14, False, True),
}.items()}


def text(draw, xy, value, style="body", color=WHITE):
    draw.text(xy, value, font=FONTS[style], fill=color)


def box(draw, bounds, fill="#121d30", outline=BORDER, radius=16):
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=1)


def thumbnail():
    """Draw a schematic motherboard as illustrative evidence."""
    image = Image.new("RGB", (240, 150), "#10192a")
    draw = ImageDraw.Draw(image)
    box(draw, (26, 12, 214, 138), "#194440", "#38756b", 8)
    for y in range(26, 130, 16):
        draw.line((34, y, 200, y), fill="#286158")
    box(draw, (91, 40, 146, 94), "#a9bac8", "#d4e3ed", 4)
    box(draw, (102, 51, 135, 83), "#3b5264", "#6c8798", 3)
    for x in (163, 178, 193):
        box(draw, (x, 30, x + 7, 105), "#e4c07f", "#e4c07f", 2)
    for y in (105, 118):
        box(draw, (46, y, 145, y + 6), "#526c78", "#526c78", 2)
    return image


def icon(draw, x, y, color, status="completed"):
    draw.ellipse((x, y, x + 22, y + 22), fill="#1e3041", outline=color)
    if status == "completed":
        draw.line((x + 6, y + 11, x + 10, y + 15, x + 17, y + 7), fill=color, width=2)
    elif status == "not_done":
        draw.line((x + 7, y + 7, x + 15, y + 15), fill=color, width=2)
        draw.line((x + 15, y + 7, x + 7, y + 15), fill=color, width=2)
    else:
        draw.line((x + 11, y + 5, x + 11, y + 12), fill=color, width=2)
        draw.ellipse((x + 10, y + 16, x + 12, y + 18), fill=color)


def fit(draw, value, width, style="body"):
    if draw.textlength(value, font=FONTS[style]) <= width:
        return value
    while draw.textlength(value + "…", font=FONTS[style]) > width:
        value = value[:-1]
    return value + "…"


def render(t, steps, verdicts, evidence):
    image = Image.new("RGB", (1120, 680))
    draw = ImageDraw.Draw(image)
    for y in range(680):
        draw.line((0, y, 1120, y), fill=(11 + int(4 * y / 680), 17 + int(6 * y / 680), 32 + int(9 * y / 680)))
    text(draw, (40, 27), "StepCheck AI", "title")
    text(draw, (41, 76), "Turn work images into a step-by-step check.", color=MUTED)
    box(draw, (829, 37, 1080, 69), "#1d2840", BORDER, 16)
    text(draw, (844, 44), "WORKFLOW PREVIEW  /  MOCK", "small", PURPLE)
    phase = 0 if t < 2.5 else 1 if t < 4.5 else 2
    box(draw, (40, 121, 515, 545))
    box(draw, (605, 121, 1080, 545))
    text(draw, (62, 143), "01  Procedure + evidence", "heading")
    text(draw, (627, 143), "02  Per-step verdicts", "heading")
    text(draw, (62, 181), "procedure.md", "small", MUTED)
    box(draw, (61, 207, 494, 396), "#0e1728", BORDER, 10)
    text(draw, (77, 220), "# PC Assembly", "mono", PURPLE)
    for i, step in enumerate(steps[:min(len(steps), int(t / 0.32) + 1)]):
        text(draw, (77, 254 + i * 26), fit(draw, f"{step.index}. {step.text}", 398, "mono"), "mono")
    if t >= 2.5:
        image.paste(evidence.resize((120, 75), Image.Resampling.LANCZOS), (77, 417))
        text(draw, (214, 425), "assembly.png", "label")
        text(draw, (214, 451), "1 work image attached", "small", MUTED)
        icon(draw, 459, 438, TEAL)
    else:
        box(draw, (61, 414, 494, 500), "#0e1728", BORDER, 10)
        text(draw, (159, 444), "Add a work image", color=MUTED)
    arrow = TEAL if t >= 4.5 else BORDER
    draw.line((533, 320, 586, 320), fill=arrow, width=3)
    draw.line((576, 311, 586, 320, 576, 329), fill=arrow, width=3)
    if t < 4.5:
        text(draw, (695, 303), "Ready when you are.", "heading", MUTED)
        text(draw, (694, 336), "One verdict for every step.", color=MUTED)
    elif t < 5.3:
        text(draw, (737, 303), "Checking…", "heading", TEAL)
        for i in range(3):
            x = 769 + 23 * i
            draw.ellipse((x, 351, x + 8, 359), fill=TEAL if int(t * 8) % 3 == i else BORDER)
    else:
        count = min(len(steps), int((t - 5.3) / 0.45) + 1)
        for i, (step, verdict) in enumerate(zip(steps[:count], verdicts[:count])):
            y = 195 + i * 61
            color = COLORS[verdict.status.value]
            box(draw, (625, y, 1059, y + 53), "#172439", BORDER, 9)
            icon(draw, 638, y + 15, color, verdict.status.value)
            text(draw, (672, y + 7), fit(draw, step.text, 366))
            text(draw, (672, y + 31), f"{LABELS[verdict.status.value]}  /  {verdict.confidence:.0%} confidence", "small", color)
        if count == len(steps):
            counts = [sum(v.status.value == status for v in verdicts) for status in LABELS]
            text(draw, (631, 511), f"{counts[0]} completed   ·   {counts[1]} not done   ·   {counts[2]} undetermined", "small", MUTED)
    for i, caption in enumerate(["Write the procedure", "Attach work images", "Review every step"]):
        x = 40 + i * 350
        active = i <= phase
        draw.rounded_rectangle((x, 580, x + 320, 584), radius=2, fill=TEAL if active else BORDER)
        text(draw, (x, 596), f"0{i + 1}", "label", TEAL if active else MUTED)
        text(draw, (x + 34, 592), caption, "heading", WHITE if active else MUTED)
    text(draw, (40, 642), "Illustrated workflow • real MockProvider values • mock does not analyze image contents", "small", MUTED)
    return image


def main():
    markdown = (ROOT / "examples" / "pc-build.md").read_text(encoding="utf-8")
    texts = re.findall(r"^\d+\. (.+)$", markdown, flags=re.MULTILINE)
    steps = [ProcedureStep(i + 1, value) for i, value in enumerate(texts)]
    evidence = thumbnail()
    buffer = io.BytesIO()
    evidence.save(buffer, format="PNG")
    verdicts = asyncio.run(MockProvider().verify(VerificationInput(
        steps=steps, images=[ImagePayload(buffer.getvalue())],
    )))
    frames = [render(i / 8, steps, verdicts, evidence) for i in range(88)]
    # A shared palette prevents flickering between frames.
    palette = frames[-1].quantize(colors=128)
    frames = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    destination = ROOT / "docs" / "assets" / "demo.gif"
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(destination, save_all=True, append_images=frames[1:],
                   duration=130, loop=0, optimize=True, disposal=1)
    print(f"Created {destination.relative_to(ROOT)} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
