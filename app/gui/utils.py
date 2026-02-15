"""wxPython utility functions for the application.

Common helpers for image conversion, widget creation, and other UI operations.
"""

import wx
from PIL import Image
from typing import Optional


def pil_to_bitmap(pil_image: Image.Image) -> wx.Bitmap:
    """Convert PIL Image to wx.Bitmap.

    Args:
        pil_image: PIL Image object

    Returns:
        wx.Bitmap ready for display
    """
    # Convert PIL image to wx.Image
    width, height = pil_image.size

    # Ensure image is in RGB mode
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')

    # Get image data as bytes
    data = pil_image.tobytes()

    # Create wx.Image from RGB data
    wx_image = wx.Image(width, height)
    wx_image.SetData(data)

    # Convert to wx.Bitmap
    return wx.Bitmap(wx_image)


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
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return wx.Colour(r, g, b)


def colour_to_hex(colour: wx.Colour) -> str:
    """Convert wx.Colour to hex string.

    Args:
        colour: wx.Colour object

    Returns:
        Hex color string like "#FFFFFF"
    """
    return f"#{colour.Red():02X}{colour.Green():02X}{colour.Blue():02X}"


def create_button(parent: wx.Window, label: str, callback: callable = None,
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
                    callback: callable = None, style: int = 0) -> wx.TextCtrl:
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
                      font: Optional[wx.Font] = None,
                      colour: Optional[wx.Colour] = None) -> wx.StaticText:
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


def show_error(parent: Optional[wx.Window], message: str, title: str = "Error"):
    """Show an error message dialog.

    Args:
        parent: Parent window (can be None)
        message: Error message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR, parent)


def show_info(parent: Optional[wx.Window], message: str, title: str = "Information"):
    """Show an information message dialog.

    Args:
        parent: Parent window (can be None)
        message: Information message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION, parent)


def show_warning(parent: Optional[wx.Window], message: str, title: str = "Warning"):
    """Show a warning message dialog.

    Args:
        parent: Parent window (can be None)
        message: Warning message text
        title: Dialog title
    """
    wx.MessageBox(message, title, wx.OK | wx.ICON_WARNING, parent)


def confirm(parent: Optional[wx.Window], message: str, title: str = "Confirm") -> bool:
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


def center_window(window: wx.Window):
    """Center a window on the screen.

    Args:
        window: Window to center
    """
    window.Centre(wx.BOTH)
