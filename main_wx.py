#!/usr/bin/env python3
"""wxPython test harness for Greeting Cards App.

This is a minimal test application to verify wxPython is working correctly.
As we migrate components, we'll build up this file to become the main entry point.
"""

import wx
from app.gui import wx_styles
from app.gui import wx_utils


class TestFrame(wx.Frame):
    """Simple test window to verify wxPython setup."""

    def __init__(self):
        super().__init__(
            parent=None,
            title="Greeting Cards - wxPython Test",
            size=(wx_styles.Layout.WINDOW_WIDTH, wx_styles.Layout.WINDOW_HEIGHT)
        )

        # Set icon (use app icon if available)
        # TODO: Set app icon when we migrate icons

        # Create main panel
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx_styles.Color.BG_PRIMARY)

        # Create sizer for layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title label
        title = wx_utils.create_static_text(
            panel,
            "wxPython Migration Test",
            font=wx_styles.Font.TITLE(),
            colour=wx_styles.Color.ACCENT
        )
        sizer.Add(title, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD * 3)

        # Status message
        status = wx_utils.create_static_text(
            panel,
            "✓ wxPython is working correctly!",
            font=wx_styles.Font.HEADING(),
            colour=wx_styles.Color.SUCCESS
        )
        sizer.Add(status, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Info text
        info = wx_utils.create_static_text(
            panel,
            "This is a test harness for the wxPython migration.\n"
            "As we migrate components, they will be integrated here.",
            font=wx_styles.Font.BODY(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(info, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD * 2)

        # Add some spacing
        sizer.AddStretchSpacer()

        # Test buttons to verify styles
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_info = wx_utils.create_button(
            panel,
            "Show Info",
            lambda: wx_utils.show_info(self, "This is an info message!", "Info Test")
        )
        button_sizer.Add(btn_info, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_warning = wx_utils.create_button(
            panel,
            "Show Warning",
            lambda: wx_utils.show_warning(self, "This is a warning!", "Warning Test")
        )
        button_sizer.Add(btn_warning, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_error = wx_utils.create_button(
            panel,
            "Show Error",
            lambda: wx_utils.show_error(self, "This is an error!", "Error Test")
        )
        button_sizer.Add(btn_error, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_confirm = wx_utils.create_button(
            panel,
            "Show Confirm",
            lambda: wx_utils.show_info(
                self,
                f"You clicked: {'Yes' if wx_utils.confirm(self, 'Are you sure?', 'Confirm Test') else 'No'}",
                "Result"
            )
        )
        button_sizer.Add(btn_confirm, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(button_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # More spacing
        sizer.AddStretchSpacer()

        # Version info
        version_text = wx_utils.create_static_text(
            panel,
            f"wxPython {wx.version()}",
            font=wx_styles.Font.SMALL(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(version_text, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Set sizer
        panel.SetSizer(sizer)

        # Center window on screen
        wx_utils.center_window(self)

        # Bind close event
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def on_close(self, event):
        """Handle window close event."""
        self.Destroy()


class TestApp(wx.App):
    """Test wxPython application."""

    def OnInit(self):
        """Initialize the application."""
        self.frame = TestFrame()
        self.frame.Show()
        return True


def main():
    """Main entry point for wxPython test."""
    app = TestApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
