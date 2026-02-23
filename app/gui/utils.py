"""wxPython utility functions for the application.

Common helpers for image conversion, widget creation, and other UI operations.
"""

from pathlib import Path

import wx
from AppKit import NSOpenPanel, NSModalResponseOK  # type: ignore[import-untyped]
from PIL import Image
from collections.abc import Callable


def open_files_and_folders(message: str, file_types: list[str]) -> list[Path]:
    """Show a native macOS open panel that can select both files and folders.

    Uses NSOpenPanel directly via pyobjc to allow unified file/folder selection,
    which wx.FileDialog cannot do on macOS.

    Args:
        message: Message displayed in the dialog
        file_types: List of allowed file extensions (e.g. ["pdf"])

    Returns:
        List of selected paths (empty if cancelled)
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
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')

    # Get image data as bytes
    data = pil_image.tobytes()

    # Create wx.Image from RGB data
    wx_image = wx.Image(width, height)
    wx_image.SetData(data)

    return wx_image


def scale_bitmap(bitmap: wx.Bitmap, scale: float) -> wx.Bitmap:
    """Scale a wx.Bitmap by a factor.

    Args:
        bitmap: Original bitmap
        scale: Scale factor (1.0 = original size, 2.0 = double, 0.5 = half)

    Returns:
        Scaled wx.Bitmap
    """
    image = bitmap.ConvertToImage()
    width = int(bitmap.GetWidth() * scale)
    height = int(bitmap.GetHeight() * scale)

    # Use high quality rescaling
    scaled_image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    return wx.Bitmap(scaled_image)


def hex_to_colour(hex_color: str) -> wx.Colour:
    """Convert hex color string to wx.Colour.

    Args:
        hex_color: Hex color string like "#FFFFFF" or "FFFFFF"

    Returns:
        wx.Colour object
    """
    from app.gui.styles import Color
    return Color.from_hex(hex_color)


def colour_to_hex(colour: wx.Colour) -> str:
    """Convert wx.Colour to hex string.

    Args:
        colour: wx.Colour object

    Returns:
        Hex color string like "#FFFFFF"
    """
    return f"#{colour.Red():02X}{colour.Green():02X}{colour.Blue():02X}"


def create_button(parent: wx.Window, label: str, callback: Callable[[], None] | None = None,
                 tooltip: str = "") -> wx.Button:
    """Create a button with common settings.

    Args:
        parent: Parent window
        label: Button label text
        callback: Optional click handler
        tooltip: Optional tooltip text

    Returns:
        wx.Button
    """
    btn = wx.Button(parent, label=label)

    if callback:
        btn.Bind(wx.EVT_BUTTON, lambda evt: callback())

    if tooltip:
        btn.SetToolTip(tooltip)

    return btn


def create_text_ctrl(parent: wx.Window, value: str = "",
                    callback: Callable[[str], None] | None = None, style: int = 0) -> wx.TextCtrl:
    """Create a text control with common settings.

    Args:
        parent: Parent window
        value: Initial text value
        callback: Optional change handler
        style: Additional wx.TextCtrl style flags

    Returns:
        wx.TextCtrl
    """
    text = wx.TextCtrl(parent, value=value, style=style)

    if callback:
        text.Bind(wx.EVT_TEXT, lambda evt: callback(evt.GetString()))

    return text


def create_static_text(parent: wx.Window, label: str,
                      font: wx.Font | None = None,
                      colour: wx.Colour | None = None) -> wx.StaticText:
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


def show_error(parent: wx.Window | None, message: str, title: str = "Error") -> None:
    """Show an error message dialog.

    Args:
        parent: Parent window (can be None)
        message: Error message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR, parent)


def show_info(parent: wx.Window | None, message: str, title: str = "Information") -> None:
    """Show an information message dialog.

    Args:
        parent: Parent window (can be None)
        message: Information message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION, parent)


def show_warning(parent: wx.Window | None, message: str, title: str = "Warning") -> None:
    """Show a warning message dialog.

    Args:
        parent: Parent window (can be None)
        message: Warning message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_WARNING, parent)


def confirm(parent: wx.Window | None, message: str, title: str = "Confirm") -> bool:
    """Show a confirmation dialog.

    Args:
        parent: Parent window (can be None)
        message: Confirmation question text
        title: Dialog title

    Returns:
        True if user clicked Yes, False otherwise
    """
    result = wx.MessageBox(message, title, wx.YES_NO | wx.ICON_QUESTION, parent)
    return result == wx.YES


def center_window(window: wx.Window) -> None:
    """Center a window on the screen.

    Args:
        window: Window to center
    """
    window.Centre(wx.BOTH)
