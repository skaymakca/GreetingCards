"""DMG background image generation.

Outputs _build/dmg/background.png (1×) and background@2x.png (2×).
dmgbuild automatically discovers the @2x variant and combines both into
a multi-page TIFF so Finder displays the sharp Retina version.

Called by scripts/dmg/__main__.py before dmgbuild; the 1× path is passed
as the "background" define to scripts/dmg/dmgbuild_settings.py.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

_ROOT = pathlib.Path(__file__).parent.parent.parent
OUTPUT = _ROOT / "_build" / "dmg" / "background.png"
OUTPUT_2X = _ROOT / "_build" / "dmg" / "background@2x.png"

# Logical 660×480 — matches the DMG window_rect exactly
WIDTH, HEIGHT = 660, 480

# Icon centres in logical pixels (match icon_locations in dmgbuild_settings.py)
APP_X, APP_Y = 152, 105  # Greeting Cards.app
APPS_X, APPS_Y = 482, 105  # Applications
ARROW_MARGIN = 60  # pixels clear of each icon edge (80pt icons)

# San Francisco variable font — Weight axis 1–1000
_SF_PATH = "/System/Library/Fonts/SFNS.ttf"
_FALLBACK_PATH = "/System/Library/Fonts/Helvetica.ttc"


def _load_font(size: int, weight: int = 400) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load SF at the given optical size and weight, or fall back to Helvetica."""
    try:
        font = ImageFont.truetype(_SF_PATH, size)
        font.set_variation_by_axes([100, size, 400, weight])  # Width, OpticalSize, GRAD, Weight
        return font
    except OSError:
        pass
    except AttributeError:
        pass
    try:
        return ImageFont.truetype(_FALLBACK_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _gradient(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    """Left-to-right gradient: steel-blue-gray → near-white."""
    left = (210, 220, 232)
    right = (246, 248, 251)
    for x in range(w):
        t = x / (w - 1)
        r = int(left[0] + t * (right[0] - left[0]))
        g = int(left[1] + t * (right[1] - left[1]))
        b = int(left[2] + t * (right[2] - left[2]))
        draw.line([(x, 0), (x, h)], fill=(r, g, b))


def _arrow(draw: ImageDraw.ImageDraw, scale: int) -> None:
    """Subtle right-pointing arrow between app icon and Applications folder."""
    y = APP_Y * scale
    x1 = (APP_X + ARROW_MARGIN) * scale
    x2 = (APPS_X - ARROW_MARGIN) * scale
    color = (155, 170, 190)

    head = 11 * scale
    # Shaft ends at the triangle base so line corners don't poke through
    draw.line([(x1, y), (x2 - head, y)], fill=color, width=3 * scale)

    draw.polygon(
        [(x2, y), (x2 - head, y - head // 2), (x2 - head, y + head // 2)],
        fill=color,
    )


def _small_caps(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, scale: int) -> None:
    """Draw text in small caps: leading caps at full size, others as smaller uppercase."""
    cap_size = 13 * scale
    small_size = int(10 * scale)
    weight = 650  # Semibold — matches Finder icon labels

    cap_font = _load_font(cap_size, weight)
    small_font = _load_font(small_size, weight)
    color = (125, 143, 165)
    spacing = int(1.5 * scale)  # letter spacing for small-caps feel

    # Measure total width for centering
    total_w = 0
    for ch in text:
        if ch == " ":
            total_w += 4 * scale
        elif ch.isupper():
            bbox = draw.textbbox((0, 0), ch, font=cap_font)
            total_w += int(bbox[2] - bbox[0]) + spacing
        else:
            bbox = draw.textbbox((0, 0), ch.upper(), font=small_font)
            total_w += int(bbox[2] - bbox[0]) + spacing
    total_w -= spacing  # no trailing space

    # Draw character by character
    cx = x - total_w // 2
    for ch in text:
        if ch == " ":
            cx += 4 * scale
            continue
        if ch.isupper():
            font = cap_font
            glyph = ch
            bbox = draw.textbbox((0, 0), glyph, font=font)
            draw.text((cx, y), glyph, fill=color, font=font)
            cx += int(bbox[2] - bbox[0]) + spacing
        else:
            font = small_font
            glyph = ch.upper()
            bbox = draw.textbbox((0, 0), glyph, font=font)
            # Align small-cap baseline with cap baseline
            cap_bbox = draw.textbbox((0, 0), "D", font=cap_font)
            small_bbox = draw.textbbox((0, 0), "D", font=small_font)
            baseline_offset = int(cap_bbox[3] - cap_bbox[1]) - int(small_bbox[3] - small_bbox[1])
            draw.text((cx, y + baseline_offset), glyph, fill=color, font=font)
            cx += int(bbox[2] - bbox[0]) + spacing


def _label(draw: ImageDraw.ImageDraw, scale: int) -> None:
    """'Drag to Install' label in small caps, centred below the arrow."""
    x1 = (APP_X + ARROW_MARGIN) * scale
    x2 = (APPS_X - ARROW_MARGIN) * scale
    centre_x = (x1 + x2) // 2
    label_y = (APP_Y + 14) * scale

    _small_caps(draw, "Drag to Install", centre_x, label_y, scale)


def _render(scale: int) -> Image.Image:
    """Render the background at the given scale factor."""
    w, h = WIDTH * scale, HEIGHT * scale
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    _gradient(draw, w, h)
    _arrow(draw, scale)
    _label(draw, scale)
    return img


def generate() -> pathlib.Path:
    """Generate 1× and @2x background images; return the 1× path."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _render(1).save(OUTPUT, "PNG")
    _render(2).save(OUTPUT_2X, "PNG")
    return OUTPUT


def main() -> None:
    path = generate()
    print(f"Generated {path}")


if __name__ == "__main__":
    main()
