"""Horror YouTube thumbnail generation using Pillow.

Template: dark atmospheric background + red vignette glow + bold white title.
Designed for 8-14% CTR based on competitor analysis (Mr. Nightmare, Corpse Husband style).

1280x720px — YouTube's required thumbnail resolution.
"""

import os
import random
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


W, H = 1280, 720

# Horror palette
BG_DARK = (8, 0, 12, 255)
TEXT_WHITE = (255, 255, 255)
TEXT_RED = (210, 15, 15)
GLOW_RED = (150, 0, 0, 120)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "C:\\Windows\\Fonts\\Impact.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fetch_horror_bg(tmp_dir: Path) -> Path | None:
    """Download a dark atmospheric image from Pexels."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return None
    queries = [
        "dark forest fog atmospheric",
        "abandoned building dark interior",
        "dark shadow figure silhouette",
        "misty night forest atmospheric",
    ]
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": random.choice(queries), "per_page": 5, "orientation": "landscape"},
            timeout=20,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        photo = random.choice(photos[:3])
        url = photo["src"]["large"]
        out = tmp_dir / "thumb_bg.jpg"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        out.write_bytes(r.content)
        return out
    except Exception:
        return None


def _draw_red_vignette(img: Image.Image) -> Image.Image:
    """Add dark red glow at corners — signature horror look."""
    vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    steps = 100
    for i in range(steps):
        alpha = int(160 * (1 - i / steps) ** 1.5)
        color = (90, 0, 0, alpha)
        draw.rectangle([i * 3, i * 2, W - i * 3, H - i * 2], outline=color)
    return Image.alpha_composite(img, vignette)


def generate_thumbnail(title: str, out_path: Path, tmp_dir: Path) -> Path:
    """Generate a horror-optimized YouTube thumbnail (1280x720)."""
    bg_photo = _fetch_horror_bg(tmp_dir)

    if bg_photo and bg_photo.exists():
        base = Image.open(bg_photo).convert("RGBA").resize((W, H), Image.LANCZOS)
        base = ImageEnhance.Brightness(base).enhance(0.30)   # Very dark
        base = ImageEnhance.Color(base).enhance(0.55)         # Desaturate toward horror
    else:
        base = Image.new("RGBA", (W, H), BG_DARK)

    # Red vignette corners
    base = _draw_red_vignette(base)
    draw = ImageDraw.Draw(base)

    # Normalize title: trim very long titles
    words = title.split()
    display = " ".join(words[:9]) + ("..." if len(words) > 9 else "")

    # Split into at most 2 lines, ~22 chars per line
    raw_lines = textwrap.fill(display, width=20).split("\n")[:2]

    font_l = _get_font(104)
    font_s = _get_font(60)

    # Vertical center
    total_h = sum(120 if i == 0 else 76 for i in range(len(raw_lines)))
    y = (H - total_h) // 2 - 20

    for idx, line in enumerate(raw_lines):
        font = font_l if idx == 0 else font_s
        text_upper = line.upper()
        bbox = draw.textbbox((0, 0), text_upper, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2

        # Red shadow layers (glow effect)
        for ox, oy in [(-4, 4), (4, -4), (-4, -4), (4, 4), (0, 6), (0, -6)]:
            draw.text((x + ox, y + oy), text_upper, fill=(180, 0, 0, 200), font=font)

        # White main text
        draw.text((x, y), text_upper, fill=TEXT_WHITE, font=font)
        y += 128 if idx == 0 else 80

    # Thin red accent bar at bottom
    draw.rectangle([0, H - 9, W, H], fill=TEXT_RED)

    base.convert("RGB").save(str(out_path), "JPEG", quality=95, optimize=True)
    return out_path
