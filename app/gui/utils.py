"""wxPython utility functions for the application.

Common helpers for image conversion, widget creation, and other UI operations.
"""

from pathlib import Path

import wx
from AppKit import NSModalResponseOK, NSOpenPanel  # type: ignore[import-untyped]
from PIL import Image

from app.gui.styles import Color, Layout


def plural(count: int, word: str) -> str:
    """Return e.g. '3 cards' or '1 card'."""
    return f"{count} {word}{'s' if count != 1 else ''}"


def open_files_and_folders(message: str, file_types: list[str]) -> list[Path]:
    """Show a native macOS open panel that can select both files and folders.

    Uses NSOpenPanel directly via pyobjc to allow unified file/folder selection,
    which wx.FileDialog cannot do on macOS.

    Args:
        message: Message displayed in the dialog
        file_types: List of allowed file extensions (e.g. ["pdf"])

    Returns:
        List of selected paths (empty if canceled)
    """
    panel = NSOpenPanel.openPanel()
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(True)
    panel.setAllowsMultipleSelection_(True)
    panel.setAllowedFileTypes_(file_types)
    panel.setMessage_(message)

    if panel.runModal() == NSModalResponseOK:
        return [Path(url.path()) for url in panel.URLs()]
    return []


def pil_to_bitmap(pil_image: Image.Image) -> wx.Bitmap:
    """Convert PIL Image to wx.Bitmap.

    Args:
        pil_image: PIL Image object

    Returns:
        wx.Bitmap ready for display
    """
    return wx.Bitmap(pil_to_image(pil_image))


def pil_to_image(pil_image: Image.Image) -> wx.Image:
    """Convert PIL Image to wx.Image.

    Args:
        pil_image: PIL Image object

    Returns:
        wx.Image (can be scaled before converting to bitmap)
    """
    width, height = pil_image.size

    # Ensure image is in RGB mode
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    # Get image data as bytes
    data = pil_image.tobytes()

    # Create wx.Image from RGB data
    wx_image = wx.Image(width, height)
    wx_image.SetData(data)

    return wx_image


def draw_drag_highlight(gc: wx.GraphicsContext, w: int, h: int) -> None:  # pragma: no cover
    """Draw a macOS-blue rounded-rectangle drag highlight border.

    Used by both DropOverlay and ReviewPanelMasterDetail to draw a consistent
    drag-active border.

    Args:
        gc: GraphicsContext to draw on
        w: Panel width
        h: Panel height
    """
    inset = Layout.HIGHLIGHT_INSET
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(Color.ACCENT).Width(Layout.HIGHLIGHT_WIDTH)))
    gc.SetBrush(wx.NullBrush)
    path = gc.CreatePath()
    path.AddRoundedRectangle(inset, inset, w - inset * 2, h - inset * 2, Layout.HIGHLIGHT_RADIUS)
    gc.StrokePath(path)


def create_static_text(
    parent: wx.Window, label: str, font: wx.Font | None = None, colour: wx.Colour | None = None
) -> wx.StaticText:
    """Create a static text label with common settings.

    Args:
        parent: Parent window
        label: Text to display
        font: Optional wx.Font
        colour: Optional text wx.Colour

    Returns:
        wx.StaticText
    """
    text = wx.StaticText(parent, label=label)

    if font:
        text.SetFont(font)

    if colour:
        text.SetForegroundColour(colour)

    return text
