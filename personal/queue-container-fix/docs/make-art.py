"""Draw the Queue Container Fix hero and icon in the pack's stipple house style."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parent
BOLD = "C:/Windows/Fonts/segoeuib.ttf"
REGULAR = "C:/Windows/Fonts/segoeui.ttf"

HERO_W, HERO_H = 1200, 600
CELL = 4


def queue_study(size: int = 620) -> Image.Image:
    """Grayscale study: one queue card, three rows, a control strip first."""
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)

    left, top, right, bottom = 40, 40, 470, 470
    d.rounded_rectangle([left, top, right, bottom], radius=30, outline=255, width=6)

    rows = [top + 70, top + 170, top + 270]
    for index, y in enumerate(rows):
        # Control strip: three dots, brightest on the row that carries controls.
        for i in range(3):
            cx = left + 46 + i * 30
            d.ellipse([cx - 8, y - 8, cx + 8, y + 8], fill=255 if index == 1 else 186)
        # Message text as two bars of different weight.
        d.rounded_rectangle([left + 148, y - 9, right - 40, y + 9], radius=9, fill=205 if index == 1 else 150)
        d.rounded_rectangle([left + 148, y + 26, right - 120, y + 40], radius=7, fill=110)

    # Dotted arcs sweeping out of the card, kept inside the card's own height.
    for ring in range(7):
        radius = 110 + ring * 44
        span = 62
        step = 3.2
        angle = -span
        fade = 1.0 - ring / 8.2
        while angle <= span:
            x = (right - 6) + radius * math.cos(math.radians(angle))
            y = (top + bottom) / 2 + radius * math.sin(math.radians(angle))
            if 0 <= x < size and 0 <= y < size:
                r = 0.8 + 2.6 * fade
                tone = int(70 + 150 * fade)
                d.ellipse([x - r, y - r, x + r, y + r], fill=tone)
            angle += step

    return img


def stipple(source: Image.Image, out_w: int, out_h: int, origin: tuple[int, int], scale: float) -> Image.Image:
    """Sample the study onto a regular dot grid; dot size carries the tone."""
    art = Image.new("RGB", (out_w, out_h), (0, 0, 0))
    d = ImageDraw.Draw(art)
    sw, sh = int(source.width * scale), int(source.height * scale)
    study = source.resize((sw, sh), Image.LANCZOS)
    off_x, off_y = origin

    for gy in range(0, sh, CELL):
        for gx in range(0, sw, CELL):
            peak = max(study.crop((gx, gy, gx + CELL, gy + CELL)).getdata())
            if peak < 40:
                continue
            amount = peak / 255.0
            radius = 0.55 + 2.5 * amount
            tone = int(120 + 135 * amount)
            cx = off_x + gx + CELL / 2
            cy = off_y + gy + CELL / 2
            d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(tone, tone, tone))
    return art


def hero() -> Image.Image:
    art = stipple(queue_study(), HERO_W, HERO_H, (60, 30), 0.86)

    d = ImageDraw.Draw(art)
    title_font = ImageFont.truetype(BOLD, 58)
    sub_font = ImageFont.truetype(REGULAR, 25)

    title = "Queue Container Fix"
    sub = "Controls at the start of every queued prompt"
    tw = d.textlength(title, font=title_font)
    sw = d.textlength(sub, font=sub_font)
    d.text(((HERO_W - tw) / 2, 452), title, font=title_font, fill=(255, 255, 255))
    d.text(((HERO_W - sw) / 2, 528), sub, font=sub_font, fill=(176, 176, 176))
    return art


def icon() -> Image.Image:
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=112, fill=(10, 10, 10, 255))

    d.rounded_rectangle([92, 148, 420, 364], radius=34, outline=(245, 245, 245, 255), width=14)

    # First row carries the control strip; both rows carry a text bar.
    for index, y in enumerate([210, 292]):
        if index == 0:
            for i in range(3):
                cx = 152 + i * 36
                d.ellipse([cx - 12, y - 12, cx + 12, y + 12], fill=(255, 255, 255, 255))
            d.rounded_rectangle([258, y - 10, 378, y + 10], radius=10, fill=(235, 235, 235, 255))
        else:
            d.rounded_rectangle([152, y - 10, 378, y + 10], radius=10, fill=(150, 150, 150, 255))
    return img


if __name__ == "__main__":
    hero_img = hero()
    hero_img.save(DOCS / "hero.png")
    print("hero", hero_img.size)
    icon_img = icon()
    icon_img.save(DOCS / "icon.png")
    print("icon", icon_img.size)
