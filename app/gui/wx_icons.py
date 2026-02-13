"""SF Symbol icon loader for wxPython using PyObjC with caching and graceful fallback."""

from __future__ import annotations

import io
import wx

# NSImage rendering constants
_NS_FONT_WEIGHT_MEDIUM = 5
_NS_IMAGE_SYMBOL_SCALE_SMALL = 1
_NS_IMAGE_SYMBOL_SCALE_MEDIUM = 2
_NS_IMAGE_INTERPOLATION_HIGH = 3
_DEFAULT_RETINA_SCALE = 2

_cache: dict[tuple[str, int, str, int], wx.Bitmap | None] = {}  # Icon cache


def _hex_to_rgb(color_hex: str) -> tuple[float, float, float]:
    """Convert hex color string to RGB floats (0.0-1.0).

    Args:
        color_hex: Hex color string (e.g., "#1D1D1F")

    Returns:
        Tuple of (red, green, blue) as floats from 0.0 to 1.0
    """
    r = int(color_hex[1:3], 16) / 255.0
    g = int(color_hex[3:5], 16) / 255.0
    b = int(color_hex[5:7], 16) / 255.0
    return r, g, b


def load_menu_icon(name: str, color_hex: str = "#1D1D1F") -> wx.Bitmap | None:
    """Load SF Symbol optimized for context/popup menus.

    Uses 6pt size with Small scale to match native macOS menu icons.

    Args:
        name: SF Symbol name (e.g., "scissors", "textformat.abc")
        color_hex: Hex color string (defaults to near-black)

    Returns:
        wx.Bitmap with the rendered symbol, or None if unavailable
    """
    return load_sf_symbol(name, point_size=6, color_hex=color_hex, scale=1)


def load_sf_symbol(
    name: str, point_size: int = 14, color_hex: str = "#1D1D1F", scale: int = 2
) -> wx.Bitmap | None:
    """Load an SF Symbol by name and return a wx.Bitmap.

    Returns None if PyObjC is not installed or the symbol is unavailable.
    Results are cached by (name, point_size, color_hex, scale).

    Args:
        name: SF Symbol name (e.g., "scissors", "doc.on.doc")
        point_size: Icon size in points
        color_hex: Hex color string (e.g., "#1D1D1F")
        scale: NSImageSymbolScale (1=Small, 2=Medium, 3=Large). Use 1 for crisp menu icons.

    Returns:
        wx.Bitmap with the rendered symbol, or None if unavailable
    """
    key = (name, point_size, color_hex, scale)
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
            point_size, _NS_FONT_WEIGHT_MEDIUM, scale
        )

        # Build color config from hex
        r, g, b = _hex_to_rgb(color_hex)
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
        render_scale = int(screen.backingScaleFactor()) if screen else _DEFAULT_RETINA_SCALE
        px_w, px_h = pt_w * render_scale, pt_h * render_scale

        # Create bitmap at native pixel resolution
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, px_w, px_h, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
        )
        # Set the rep's point size so drawing scales up into the larger pixel buffer
        rep.setSize_(NSSize(pt_w, pt_h))

        ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(ctx)

        # Use high quality interpolation for smooth rendering
        ctx.setImageInterpolation_(_NS_IMAGE_INTERPOLATION_HIGH)

        styled.drawInRect_fromRect_operation_fraction_(
            NSRect(NSPoint(0, 0), NSSize(pt_w, pt_h)),
            NSRect(NSPoint(0, 0), NSSize(0, 0)),  # entire image
            NSCompositingOperationSourceOver,
            1.0,
        )
        NSGraphicsContext.restoreGraphicsState()

        # Convert to PNG bytes then wx.Bitmap
        png_data = rep.representationUsingType_properties_(NSPNGFileType, None)
        if png_data is None:
            _cache[key] = None
            return None

        png_bytes = bytes(png_data)

        # Convert PNG bytes to wx.Bitmap directly via wx.Image
        wx_img = wx.Image(io.BytesIO(png_bytes))
        if not wx_img.IsOk():
            _cache[key] = None
            return None
        bitmap = wx.Bitmap(wx_img)

        _cache[key] = bitmap
        return bitmap

    except (ImportError, AttributeError, RuntimeError):
        # ImportError: PyObjC not available
        # AttributeError: NSImage/AppKit API issues
        # RuntimeError: Image rendering failures
        _cache[key] = None
        return None
