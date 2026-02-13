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
from app.gui.wx_dialogs import ProgressDialog, CompletionDialog, RenameConfirmDialog, ErrorListDialog
from app.gui.wx_help_dialog import show_help_dialog
from app.gui.wx_settings_dialog import show_settings_dialog
from app.models.card import RenameResult, RenamePlanItem


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

        # Phase 3 dialog tests
        dialog_sizer2 = wx.BoxSizer(wx.HORIZONTAL)

        btn_help = wx_utils.create_button(
            panel,
            "Help Dialog",
            self._test_help
        )
        dialog_sizer2.Add(btn_help, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_settings = wx_utils.create_button(
            panel,
            "Settings Dialog",
            self._test_settings
        )
        dialog_sizer2.Add(btn_settings, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_rename_confirm = wx_utils.create_button(
            panel,
            "Rename Confirm",
            self._test_rename_confirm
        )
        dialog_sizer2.Add(btn_rename_confirm, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_error_list = wx_utils.create_button(
            panel,
            "Error List",
            self._test_error_list
        )
        dialog_sizer2.Add(btn_error_list, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(dialog_sizer2, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 4 icon and context menu tests
        phase4_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_icons = wx_utils.create_button(
            panel,
            "SF Symbols Test",
            self._test_icons
        )
        phase4_sizer.Add(btn_icons, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_context = wx_utils.create_button(
            panel,
            "Context Menu Test",
            self._test_context_menu
        )
        phase4_sizer.Add(btn_context, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(phase4_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

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

    def _test_help(self):
        """Test help dialog."""
        show_help_dialog(self)

    def _test_settings(self):
        """Test settings dialog."""
        show_settings_dialog(self)

    def _test_rename_confirm(self):
        """Test rename confirm dialog."""
        # Create mock rename plan
        plan = [
            RenamePlanItem(
                Path("card1.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                "ok"
            ),
            RenamePlanItem(
                Path("card2.pdf"),
                Path("Holiday Cards 2024 - Johnson Family.pdf"),
                "ok"
            ),
            RenamePlanItem(
                Path("card3.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                "duplicate"
            ),
            RenamePlanItem(
                Path("card4.pdf"),
                Path("card4.pdf"),
                "skip_same"
            ),
            RenamePlanItem(
                Path("card5.pdf"),
                Path("card5.pdf"),
                "skip_no_name"
            ),
            RenamePlanItem(
                Path("card6.pdf"),
                Path("card6.pdf"),
                "skip_error"
            ),
        ]

        dialog = RenameConfirmDialog(self, plan, "2024")
        result = dialog.ShowModal()
        dialog.Destroy()

        if result == wx.ID_OK:
            wx_utils.show_info(self, "User clicked Rename All", "Result")
        else:
            wx_utils.show_info(self, "User clicked Cancel", "Result")

    def _test_error_list(self):
        """Test error list dialog."""
        # Create mock errors
        errors = [
            ("card1.pdf", "Authentication failed"),
            ("card2.pdf", "Timeout exceeded"),
            ("card3.pdf", "Invalid response format"),
            ("card4.pdf", "Permission denied"),
        ]

        dialog = ErrorListDialog(self, "AI Analysis Errors", errors, auth_aborted=True)
        dialog.ShowModal()
        dialog.Destroy()

    def _test_icons(self):
        """Test SF Symbol icon loading at various sizes."""
        from app.gui import wx_icons

        # Create a dialog to show various icons and sizes
        dialog = wx.Dialog(self, title="SF Symbol Icons Test", size=(550, 550))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(wx_styles.Layout.PAD * 2)

        # Title
        title = wx_utils.create_static_text(
            dialog,
            "SF Symbol Icon Test",
            font=wx_styles.Font.TITLE(),
            colour=wx_styles.Color.ACCENT
        )
        sizer.Add(title, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        sizer.AddSpacer(wx_styles.Layout.PAD)

        # Test various icons at different sizes
        test_configs = [
            ("scissors", "Cut (12pt)", 12),
            ("doc.on.doc", "Copy (12pt)", 12),
            ("textformat.abc", "Title Case (12pt)", 12),
            ("xmark.circle", "Clear (12pt)", 12),
            ("scissors", "Cut (16pt)", 16),
            ("textformat.abc", "Title Case (20pt)", 20),
        ]

        for symbol_name, label, pt_size in test_configs:
            row = wx.BoxSizer(wx.HORIZONTAL)

            # Load icon at specified size
            bitmap = wx_icons.load_sf_symbol(symbol_name, pt_size, "#1D1D1F")

            if bitmap:
                icon_ctrl = wx.StaticBitmap(dialog, bitmap=bitmap)
                row.Add(icon_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, wx_styles.Layout.PAD)
                status = "✓"
            else:
                # Show placeholder if icon failed to load
                placeholder = wx_utils.create_static_text(dialog, "[?]")
                row.Add(placeholder, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, wx_styles.Layout.PAD)
                status = "✗"

            # Label
            text = wx_utils.create_static_text(
                dialog,
                f"{label} {status}",
                font=wx_styles.Font.BODY()
            )
            row.Add(text, 0, wx.ALIGN_CENTER_VERTICAL)

            sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, wx_styles.Layout.PAD * 2)

        sizer.AddSpacer(wx_styles.Layout.PAD * 3)

        # OK button
        ok_btn = wx.Button(dialog, wx.ID_OK, "OK")
        ok_btn.SetMinSize((120, 32))
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.ALL, wx_styles.Layout.PAD * 2)

        dialog.SetSizer(sizer)
        dialog.CenterOnParent()
        dialog.ShowModal()
        dialog.Destroy()

    def _test_context_menu(self):
        """Test context menu with SF Symbol icons."""
        from app.gui import wx_context_menu

        # Create a dialog with a text field that has the context menu
        dialog = wx.Dialog(self, title="Context Menu Test", size=(400, 250))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(20)

        # Title
        title = wx.StaticText(dialog, label="Context Menu Test")
        title.SetFont(wx_styles.Font.TITLE())
        sizer.Add(title, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(10)

        # Instructions
        instructions = wx.StaticText(
            dialog,
            label="Right-click the text field below to see the context menu\n"
                  "with SF Symbol icons (Cut, Copy, Paste, Title Case, Clear)."
        )
        instructions.SetFont(wx_styles.Font.BODY())
        sizer.Add(instructions, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        # Text field with context menu
        text_ctrl = wx.TextCtrl(
            dialog,
            value="hello world - right click me!",
            size=(360, -1)
        )
        text_ctrl.SetFont(wx_styles.Font.BODY())
        wx_context_menu.add_entry_context_menu(text_ctrl)
        sizer.Add(text_ctrl, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddStretchSpacer()

        # OK button
        ok_btn = wx.Button(dialog, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 20)

        dialog.SetSizer(sizer)
        dialog.CenterOnParent()
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
