"""SF Symbol icon loader using PyObjC with caching and graceful fallback."""

from __future__ import annotations

import io
from tkinter import PhotoImage

_cache: dict[tuple[str, int, str], PhotoImage | None] = {}  # Icon cache


def load_sf_symbol(
    name: str, point_size: int = 14, color_hex: str = "#1D1D1F"
) -> PhotoImage | None:
    """Load an SF Symbol by name and return a tk PhotoImage.

    Returns None if PyObjC is not installed or the symbol is unavailable.
    Results are cached by (name, point_size, color_hex).
    """
    key = (name, point_size, color_hex)
    if key in _cache:
        return _cache[key]

    try:
        from AppKit import (
            NSImage,
            NSImageSymbolConfiguration,
            NSBitmapImageRep,
            NSColor,
            NSGraphicsContext,
            NSCompositingOperationSourceOver,
            NSPNGFileType,
            NSScreen,
        )
        from Foundation import NSSize, NSRect, NSPoint

        # Load the SF Symbol
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if image is None:
            _cache[key] = None
            return None

        # Build size config
        size_config = NSImageSymbolConfiguration.configurationWithPointSize_weight_scale_(
            point_size, 5, 2  # NSFontWeightMedium=5, NSImageSymbolScaleMedium=2
        )

        # Build color config from hex
        r = int(color_hex[1:3], 16) / 255.0
        g = int(color_hex[3:5], 16) / 255.0
        b = int(color_hex[5:7], 16) / 255.0
        ns_color = NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
        color_config = NSImageSymbolConfiguration.configurationWithHierarchicalColor_(ns_color)

        # Combine configs and apply
        combined = size_config.configurationByApplyingConfiguration_(color_config)
        styled = image.imageWithSymbolConfiguration_(combined)
        if styled is None:
            styled = image

        # Get point size and screen scale factor for Retina support
        sz = styled.size()
        pt_w, pt_h = int(sz.width), int(sz.height)
        if pt_w == 0 or pt_h == 0:
            _cache[key] = None
            return None

        screen = NSScreen.mainScreen()
        scale = int(screen.backingScaleFactor()) if screen else 2
        px_w, px_h = pt_w * scale, pt_h * scale

        # Create bitmap at native pixel resolution
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, px_w, px_h, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
        )
        # Set the rep's point size so drawing scales up into the larger pixel buffer
        rep.setSize_(NSSize(pt_w, pt_h))

        ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(ctx)
        styled.drawInRect_fromRect_operation_fraction_(
            NSRect(NSPoint(0, 0), NSSize(pt_w, pt_h)),
            NSRect(NSPoint(0, 0), NSSize(0, 0)),  # entire image
            NSCompositingOperationSourceOver,
            1.0,
        )
        NSGraphicsContext.restoreGraphicsState()

        # Convert to PNG bytes then PhotoImage
        png_data = rep.representationUsingType_properties_(NSPNGFileType, None)
        if png_data is None:
            _cache[key] = None
            return None

        png_bytes = bytes(png_data)
        try:
            from PIL import Image, ImageTk

            pil_img = Image.open(io.BytesIO(png_bytes))
            photo = ImageTk.PhotoImage(pil_img)
        except ImportError:
            import base64

            photo = PhotoImage(data=base64.b64encode(png_bytes))

        _cache[key] = photo
        return photo

    except Exception:
        _cache[key] = None
        return None
