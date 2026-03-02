"""wxPython API Key dialog using native text entry."""

import wx


def show_api_key_dialog(parent: wx.Window) -> str | None:
    """Show native API key dialog and return the key if entered.

    Uses wx.TextEntryDialog which creates a native macOS dialog with
    system appearance. The caller is responsible for persisting the key.

    Args:
        parent: Parent window

    Returns:
        API key string if entered, None if canceled or empty
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
                return result
        return None
    finally:
        dlg.Destroy()
