"""DMG background image generation.

Outputs _build/dmg/background.png (1×) and background@2x.png (2×).
dmgbuild automatically discovers the @2x variant and combines both into
a multipage TIFF so Finder displays the sharp Retina version.

Called by scripts/dmg/__main__.py before dmgbuild; the 1× path is passed
as the "background" define to scripts/dmg/dmgbuild_settings.py.
"""

import io
import pathlib

from PIL import Image, ImageDraw

_ROOT = pathlib.Path(__file__).parent.parent.parent
OUTPUT = _ROOT / "_build" / "dmg" / "background.png"
OUTPUT_2X = _ROOT / "_build" / "dmg" / "background@2x.png"

# Logical 660×480 — matches the DMG window_rect exactly
WIDTH, HEIGHT = 660, 480

# Icon centres in logical pixels (match icon_locations in dmgbuild_settings.py)
APP_X, APP_Y = 152, 105  # Greeting Cards.app
APPS_X, APPS_Y = 482, 105  # Applications

# Chevron colour — matches the steel-blue palette of the gradient
_CHEVRON_COLOR = (155, 170, 190)

# SF Symbol point size (logical pixels) — tuned for visual balance between icons
_CHEVRON_PT = 44


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


def _sf_chevron(scale: int) -> Image.Image:
    """Render SF Symbol `chevron.right` at Black weight via PyObjC.

    Returns an RGBA PIL Image at the given scale factor.
    """
    import AppKit
    import Foundation

    symbol_name = "chevron.right"
    pt_size = _CHEVRON_PT * scale

    # Create the symbol image
    ns_image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
    if ns_image is None:
        msg = f"SF Symbol '{symbol_name}' not found"
        raise RuntimeError(msg)

    # Configure for Black weight, large scale
    config = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
        pt_size, AppKit.NSFontWeightBlack, AppKit.NSImageSymbolScaleLarge
    )
    ns_image = ns_image.imageWithSymbolConfiguration_(config)

    # Get the symbol's pixel size
    size = ns_image.size()
    px_w = int(size.width)
    px_h = int(size.height)

    # Render to a bitmap
    init = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_
    rep = init(None, px_w, px_h, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)

    # Draw into the bitmap context
    AppKit.NSGraphicsContext.saveGraphicsState()
    ctx = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    AppKit.NSGraphicsContext.setCurrentContext_(ctx)

    # Tint with the chevron colour
    r, g, b = _CHEVRON_COLOR
    color = AppKit.NSColor.colorWithDeviceRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, 1.0)
    color.set()
    rect = Foundation.NSMakeRect(0, 0, px_w, px_h)
    ns_image.drawInRect_fromRect_operation_fraction_(
        rect, Foundation.NSZeroRect, AppKit.NSCompositingOperationSourceOver, 1.0
    )
    # Apply tint: redraw with SourceAtop to recolor while preserving alpha
    AppKit.NSRectFillUsingOperation(rect, AppKit.NSCompositingOperationSourceAtop)

    AppKit.NSGraphicsContext.restoreGraphicsState()

    # Convert to PIL via PNG bytes
    png_data = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    return Image.open(io.BytesIO(bytes(png_data))).convert("RGBA")


def _render(scale: int) -> Image.Image:
    """Render the background at the given scale factor."""
    w, h = WIDTH * scale, HEIGHT * scale
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    _gradient(draw, w, h)

    # Composite the SF Symbol chevron between app and Applications icons
    chevron = _sf_chevron(scale)
    cx = (APP_X + APPS_X) // 2 * scale
    cy = APP_Y * scale
    paste_x = cx - chevron.width // 2
    paste_y = cy - chevron.height // 2
    img.paste(chevron, (paste_x, paste_y), chevron)

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
