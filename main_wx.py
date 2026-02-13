#!/usr/bin/env python3
"""wxPython test harness for Greeting Cards App.

This is a minimal test application to verify wxPython is working correctly.
As we migrate components, we'll build up this file to become the main entry point.
"""

import wx
import time
from pathlib import Path
from app.gui import wx_styles
from app.gui import wx_utils
from app.gui.wx_api_key_dialog import show_api_key_dialog
from app.gui.wx_dialogs import ProgressDialog, CompletionDialog
from app.models.card import RenameResult


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

        # Phase 2 dialog tests
        dialog_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_api_key = wx_utils.create_button(
            panel,
            "API Key Dialog",
            self._test_api_key
        )
        dialog_sizer.Add(btn_api_key, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_progress = wx_utils.create_button(
            panel,
            "Progress Dialog",
            self._test_progress
        )
        dialog_sizer.Add(btn_progress, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_completion = wx_utils.create_button(
            panel,
            "Completion Dialog",
            self._test_completion
        )
        dialog_sizer.Add(btn_completion, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(dialog_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

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

    def _test_api_key(self):
        """Test API key dialog."""
        api_key = show_api_key_dialog(self)

        if api_key:
            wx_utils.show_info(self, f"API Key entered: {api_key[:10]}...", "Success")
        else:
            wx_utils.show_info(self, "API Key dialog cancelled", "Cancelled")

    def _test_progress(self):
        """Test progress dialog."""
        total = 10
        progress = ProgressDialog(self, "Processing Test", total)
        progress.Show()

        # Simulate work
        for i in range(1, total + 1):
            wx.MilliSleep(300)  # Simulate work
            progress.update_progress(i, f"Processing item {i}...")

        progress.finish()
        wx_utils.show_info(self, "Progress test complete!", "Done")

    def _test_completion(self):
        """Test completion dialog."""
        # Create mock results
        results = [
            RenameResult(
                Path("card1.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                True,
                "Renamed"
            ),
            RenameResult(
                Path("card2.pdf"),
                Path("Holiday Cards 2024 - Johnson Family.pdf"),
                True,
                "Renamed"
            ),
            RenameResult(
                Path("card3.pdf"),
                Path("card3.pdf"),
                True,
                "Already named correctly"
            ),
            RenameResult(
                Path("card4.pdf"),
                Path("Holiday Cards 2024 - Brown Family.pdf"),
                False,
                "Permission denied"
            ),
        ]

        dialog = CompletionDialog(self, "Rename Complete", results)
        dialog.ShowModal()
        dialog.Destroy()


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
