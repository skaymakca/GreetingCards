"""wxPython API Key dialog using native text entry."""

import wx

from app.core.config import save_api_key


def show_api_key_dialog(parent: wx.Window) -> str | None:
    """Show native API key dialog, save if entered, and return the key.

    Uses wx.TextEntryDialog which creates a native macOS dialog with
    system appearance. On OK, persists the key via save_api_key().

    Args:
        parent: Parent window

    Returns:
        API key string if entered and saved, None if canceled or empty
    """
    dlg = wx.TextEntryDialog(
        parent,
        message="Enter your Anthropic API key:",
        caption="API Key",
        value="",
        style=wx.OK | wx.CANCEL | wx.TE_PASSWORD,
    )

    try:
        if dlg.ShowModal() == wx.ID_OK:
            result = dlg.GetValue().strip()
            if result:
                save_api_key(result)
                return result
        return None
    finally:
        dlg.Destroy()
