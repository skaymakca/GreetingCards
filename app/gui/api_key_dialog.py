"""wxPython API Key dialog using native text entry."""

import wx


def show_api_key_dialog(parent) -> str | None:
    """Show native API key dialog and return the entered key.

    Uses wx.TextEntryDialog which creates a native macOS dialog with
    system appearance.

    Args:
        parent: Parent window

    Returns:
        API key string if entered, None if cancelled or empty
    """
    dlg = wx.TextEntryDialog(
        parent,
        message="Enter your Anthropic API key:",
        caption="API Key",
        value="",
        style=wx.OK | wx.CANCEL | wx.TE_PASSWORD  # Native dialog with password field
    )

    if dlg.ShowModal() == wx.ID_OK:
        result = dlg.GetValue().strip()
        dlg.Destroy()
        return result if result else None

    dlg.Destroy()
    return None
