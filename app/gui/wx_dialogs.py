"""wxPython dialog classes for the application."""

import wx
from pathlib import Path
from app.gui import wx_styles
from app.models.card import RenamePlanItem, RenameResult


class ProgressDialog(wx.Dialog):
    """Modal progress dialog for batch processing."""

    def __init__(self, parent, title: str, total: int):
        super().__init__(
            parent,
            title=title,
            style=wx.CAPTION  # No close button
        )

        self._total = total
        self._current = 0

        # Create panel
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx_styles.Color.BG_PRIMARY)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Message label
        self.label = wx.StaticText(panel, label="Processing...")
        self.label.SetFont(wx_styles.Font.BODY())
        self.label.SetForegroundColour(wx_styles.Color.TEXT_PRIMARY)
        sizer.Add(self.label, 0, wx.ALL, 20)

        # Progress bar
        self.progress = wx.Gauge(panel, range=total, size=(350, -1))
        sizer.Add(self.progress, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Count label
        self.count_label = wx.StaticText(panel, label=f"0 / {total}")
        self.count_label.SetFont(wx_styles.Font.SMALL())
        self.count_label.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(self.count_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Set sizers
        panel.SetSizer(sizer)
        sizer.Fit(panel)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        dialog_sizer.Fit(self)

        # Center on parent
        self.CenterOnParent()

        # Prevent closing
        self.Bind(wx.EVT_CLOSE, lambda evt: None)

    def update_progress(self, current: int, message: str = ""):
        """Update progress bar and labels.

        Args:
            current: Current progress value
            message: Optional message to display
        """
        self._current = current
        self.progress.SetValue(current)
        self.count_label.SetLabel(f"{current} / {self._total}")
        if message:
            self.label.SetLabel(message)

        # Force UI update
        wx.SafeYield()

    def finish(self):
        """Close the dialog."""
        self.EndModal(wx.ID_OK)
        self.Destroy()


class CompletionDialog(wx.Dialog):
    """Dialog showing rename results in a structured table."""

    def __init__(self, parent, title: str, results: list[RenameResult]):
        super().__init__(
            parent,
            title=title,
            size=(650, 420),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        # Compute counts
        renamed = sum(1 for r in results if r.success and r.message == "Renamed")
        skipped = sum(1 for r in results if r.success and r.message != "Renamed")
        errors = sum(1 for r in results if not r.success)

        # Create panel
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx_styles.Color.BG_PRIMARY)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with symbol and counts
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Symbol
        if errors:
            symbol = "\u26A0"
            symbol_color = wx_styles.Color.ERROR
        else:
            symbol = "\u2713"
            symbol_color = wx_styles.Color.SUCCESS

        symbol_label = wx.StaticText(panel, label=symbol)
        symbol_font = wx_styles.Font.TITLE()
        symbol_font.SetPointSize(20)
        symbol_label.SetFont(symbol_font)
        symbol_label.SetForegroundColour(symbol_color)
        header_sizer.Add(symbol_label, 0, wx.RIGHT, 8)

        # Counts text
        counts = f"{renamed} renamed, {skipped} skipped"
        if errors:
            counts += f", {errors} failed"

        counts_label = wx.StaticText(panel, label=counts)
        counts_label.SetFont(wx_styles.Font.HEADING())
        counts_label.SetForegroundColour(wx_styles.Color.TEXT_PRIMARY)
        header_sizer.Add(counts_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(header_sizer, 0, wx.ALL, 15)

        # List control for results
        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = [r for r in results if not r.success or r.message == "Renamed"]

        self.list_ctrl = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES
        )
        self.list_ctrl.SetFont(wx_styles.Font.MONO())

        # Add columns
        self.list_ctrl.InsertColumn(0, "Filename", width=500)
        self.list_ctrl.InsertColumn(1, "Result", width=70)

        # Add items
        for r in visible:
            display_name = r.new_path.name if r.success else r.old_path.name
            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), display_name)

            if r.success:
                self.list_ctrl.SetItem(index, 1, "OK")
                self.list_ctrl.SetItemTextColour(index, wx_styles.Color.SUCCESS)
            else:
                self.list_ctrl.SetItem(index, 1, "ERROR")
                self.list_ctrl.SetItemTextColour(index, wx_styles.Color.ERROR)

                # Add error detail as next row
                index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), f"    {r.message}")
                self.list_ctrl.SetItemTextColour(index, wx_styles.Color.ERROR)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        # OK button
        ok_btn = wx.Button(panel, wx.ID_OK, "OK")
        ok_btn.SetFont(wx_styles.Font.BODY())
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 15)

        # Set sizers
        panel.SetSizer(sizer)

        # Center on parent
        self.CenterOnParent()

        # Bind events
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_OK))
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE):
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()
