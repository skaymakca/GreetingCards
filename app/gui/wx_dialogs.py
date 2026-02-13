"""wxPython dialog classes for the application."""

import wx
import wx.dataview as dv
from pathlib import Path
from app.gui import wx_styles
from app.models.card import RenamePlanItem, RenameResult


class TableModel(dv.PyDataViewModel):
    """DataViewModel for tables with colored rows."""

    def __init__(self, data, colors):
        """Initialize model.

        Args:
            data: List of lists (rows x columns)
            colors: List of wx.Colour for each row
        """
        dv.PyDataViewModel.__init__(self)
        self.data = data
        self.colors = colors

    def GetColumnCount(self):
        """Return number of columns."""
        return len(self.data[0]) if self.data else 0

    def GetChildren(self, parent, children):
        """Return list of children for parent item."""
        # For a flat list, root has all items as children
        if not parent:
            for i in range(len(self.data)):
                children.append(self.ObjectToItem(i))
            return len(self.data)
        return 0

    def IsContainer(self, item):
        """Check if item is a container (has children)."""
        # Only root is a container
        return not item

    def GetParent(self, item):
        """Return parent of item."""
        # All items have root as parent
        return dv.NullDataViewItem

    def GetValue(self, item, col):
        """Return value for item and column."""
        row = self.ItemToObject(item)
        return self.data[row][col]

    def GetAttr(self, item, col, attr):
        """Set display attributes for item."""
        row = self.ItemToObject(item)
        if row < len(self.colors):
            attr.SetColour(self.colors[row])
            return True
        return False


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


class RenameConfirmDialog(wx.Dialog):
    """Dialog showing the rename plan and asking for confirmation."""

    def __init__(self, parent, plan: list[RenamePlanItem], year: str):
        super().__init__(
            parent,
            title="Confirm Rename",
            size=(700, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.result = False

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(20)

        # Header
        header = wx.StaticText(self, label="Rename Plan")
        header.SetFont(wx_styles.Font.TITLE())
        header.SetForegroundColour(wx_styles.Color.TEXT_PRIMARY)
        sizer.Add(header, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(4)

        # Summary counts
        ok_count = sum(1 for item in plan if item.status == "ok")
        dup_count = sum(1 for item in plan if item.status == "duplicate")
        error_count = sum(1 for item in plan if item.status == "skip_error")
        skip_count = sum(1 for item in plan if item.status.startswith("skip") and item.status != "skip_error")

        summary = f"{ok_count} rename(s)"
        if dup_count:
            summary += f", {dup_count} duplicate(s)"
        if skip_count:
            summary += f", {skip_count} skipped"
        if error_count:
            summary += f", {error_count} error(s)"

        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(wx_styles.Font.BODY())
        summary_label.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        sizer.Add(summary_label, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(12)

        # Status labels and colors
        STATUS_LABELS = {
            "ok": "OK", "duplicate": "DUP",
            "skip_no_name": "SKIP", "skip_same": "SAME", "skip_error": "ERROR",
        }
        STATUS_COLORS = {
            "ok": wx_styles.Color.SUCCESS,
            "duplicate": wx_styles.Color.TEXT_PRIMARY,
            "skip_no_name": wx_styles.Color.TEXT_SECONDARY,
            "skip_same": wx_styles.Color.TEXT_SECONDARY,
            "skip_error": wx_styles.Color.ERROR,
        }

        # Prepare data and colors
        data = []
        colors = []
        for item in plan:
            new_name = item.new_path.name if item.status not in ("skip_no_name", "skip_same", "skip_error") else "-"
            status_text = STATUS_LABELS.get(item.status, item.status)
            data.append([item.old_path.name, new_name, status_text])
            colors.append(STATUS_COLORS.get(item.status, wx_styles.Color.TEXT_PRIMARY))

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(
            self,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )
        self.list_ctrl.SetFont(wx_styles.Font.MONO())
        self.list_ctrl.AssociateModel(self.model)

        # Add columns
        self.list_ctrl.AppendTextColumn("Original Filename", 0, width=270)
        self.list_ctrl.AppendTextColumn("New Filename", 1, width=270)
        self.list_ctrl.AppendTextColumn("Status", 2, width=70)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        confirm_btn = wx.Button(self, wx.ID_OK, "Rename All")
        confirm_btn.Bind(wx.EVT_BUTTON, self._on_confirm)
        btn_sizer.Add(confirm_btn, 0, wx.RIGHT, 8)

        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_confirm(self, event):
        """Handle Rename All button."""
        self.result = True
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        """Handle Cancel button."""
        self.result = False
        self.EndModal(wx.ID_CANCEL)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_confirm(event)
        elif key_code == wx.WXK_ESCAPE:
            self._on_cancel(event)
        else:
            event.Skip()


class ErrorListDialog(wx.Dialog):
    """Dialog showing AI analysis errors in a structured table."""

    def __init__(self, parent, title: str, errors: list[tuple[str, str]], auth_aborted: bool = False):
        super().__init__(
            parent,
            title=title,
            size=(650, 400),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(20)

        # Summary header
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        symbol = wx.StaticText(self, label="\u26A0")
        symbol_font = wx_styles.Font.TITLE()
        symbol_font.SetPointSize(20)
        symbol.SetFont(symbol_font)
        symbol.SetForegroundColour(wx_styles.Color.ERROR)
        header_sizer.Add(symbol, 0, wx.RIGHT, 8)

        summary = f"{len(errors)} error(s)"
        if auth_aborted:
            summary += " — batch aborted"
        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(wx_styles.Font.HEADING())
        summary_label.SetForegroundColour(wx_styles.Color.TEXT_PRIMARY)
        header_sizer.Add(summary_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(header_sizer, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(12)

        # Prepare data and colors (all errors in red)
        data = [[filename, error_msg] for filename, error_msg in errors]
        colors = [wx_styles.Color.ERROR] * len(errors)

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(
            self,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )
        self.list_ctrl.SetFont(wx_styles.Font.MONO())
        self.list_ctrl.AssociateModel(self.model)

        # Add columns
        self.list_ctrl.AppendTextColumn("Filename", 0, width=300)
        self.list_ctrl.AppendTextColumn("Error", 1, width=300)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        # OK button
        ok_btn = wx.Button(self, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(20)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE):
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()


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

        sizer.AddSpacer(20)

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

        sizer.Add(header_sizer, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(12)

        # List control for results
        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = [r for r in results if not r.success or r.message == "Renamed"]

        self.list_ctrl = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES
        )
        self.list_ctrl.SetFont(wx_styles.Font.MONO())

        # Add columns with proper widths (total should match dialog width - margins)
        # Dialog width 650 - margins (20 * 2) = 610 for list control
        self.list_ctrl.InsertColumn(0, "Filename", width=500)
        self.list_ctrl.InsertColumn(1, "Result", width=110)

        # Add items
        for r in visible:
            display_name = r.new_path.name if r.success else r.old_path.name
            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), display_name)

            if r.success:
                self.list_ctrl.SetItem(index, 1, "OK")
                self.list_ctrl.SetItemTextColour(index, wx_styles.Color.SUCCESS)
            else:
                # Put error message directly in Result column
                error_text = f"ERROR\n{r.message}"
                self.list_ctrl.SetItem(index, 1, error_text)
                self.list_ctrl.SetItemTextColour(index, wx_styles.Color.ERROR)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        # OK button
        ok_btn = wx.Button(panel, wx.ID_OK, "OK")
        ok_btn.SetFont(wx_styles.Font.BODY())
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(20)

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
