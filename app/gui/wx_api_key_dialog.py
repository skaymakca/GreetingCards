"""wxPython API Key dialog."""

import wx
from app.gui import wx_styles


class ApiKeyDialog(wx.Dialog):
    """Modal dialog for entering the Anthropic API key."""

    def __init__(self, parent):
        super().__init__(
            parent,
            title="API Key",
            style=wx.DEFAULT_DIALOG_STYLE
        )

        self.result: str | None = None

        # Create main panel
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx_styles.Color.BG_PRIMARY)

        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Label
        label = wx.StaticText(
            panel,
            label="Enter your Anthropic API key:"
        )
        label.SetFont(wx_styles.Font.BODY())
        label.SetForegroundColour(wx_styles.Color.TEXT_PRIMARY)
        main_sizer.Add(label, 0, wx.ALL, 20)

        # Password entry
        self._entry = wx.TextCtrl(
            panel,
            size=(380, -1),
            style=wx.TE_PASSWORD  # Show * for password
        )
        self._entry.SetFont(wx_styles.Font.BODY())
        main_sizer.Add(self._entry, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Button sizer
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        # Save button
        save_btn = wx.Button(panel, label="Save")
        save_btn.SetFont(wx_styles.Font.HEADING())
        save_btn.Bind(wx.EVT_BUTTON, self._on_save)
        btn_sizer.Add(save_btn, 0, wx.RIGHT, 8)

        # Cancel button
        cancel_btn = wx.Button(panel, label="Cancel")
        cancel_btn.SetFont(wx_styles.Font.BODY())
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Set panel sizer
        panel.SetSizer(main_sizer)
        main_sizer.Fit(panel)

        # Set dialog sizer
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        dialog_sizer.Fit(self)

        # Set focus to entry
        self._entry.SetFocus()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

        # Center on parent
        self.CenterOnParent()

    def _on_save(self, event):
        """Handle Save button click."""
        key = self._entry.GetValue().strip()
        if key:
            self.result = key
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        """Handle Cancel button click."""
        self.result = None
        self.EndModal(wx.ID_CANCEL)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_RETURN or key_code == wx.WXK_NUMPAD_ENTER:
            # Enter key - save
            self._on_save(event)
        elif key_code == wx.WXK_ESCAPE:
            # Escape key - cancel
            self._on_cancel(event)
        else:
            # Let other keys pass through
            event.Skip()
