"""wxPython dialog classes for the application."""

import wx
import wx.dataview as dv
from pathlib import Path
from app.gui import styles
from app.models.card import (
    RenamePlanItem, RenameResult,
    STATUS_OK, STATUS_SKIP_NO_NAME, STATUS_SKIP_SAME, STATUS_SKIP_ERROR, STATUS_DUPLICATE,
)


# Dialog layout constants
_DIALOG_PADDING = 20          # Outer margin for dialog content
_HEADER_GAP = 4               # Gap between header and summary text
_SECTION_GAP = 12             # Gap between summary and table/content
_BTN_GAP = 8                  # Gap between adjacent buttons
_SCROLLBAR_WIDTH = 20         # Reserve space for vertical scrollbar
_STATUS_COL_WIDTH = 100       # Width for short status columns (OK, SKIP, SAME, ERROR, DUP)
_RESULT_COL_WIDTH = 140       # Width for result columns (OK, ERROR: msg)


def _display_path(path: Path) -> str:
    """Format a path as ~/relative for display (or just filename if under home)."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


class TableModel(dv.PyDataViewModel):
    """DataViewModel for tables with colored rows."""

    def __init__(self, data: list[list[str]], colors: list[wx.Colour]):
        """Initialize model.

        Args:
            data: List of lists (rows x columns)
            colors: List of wx.Colour for each row
        """
        super().__init__()
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


def _dismiss_on_key(dialog: wx.Dialog, event: wx.KeyEvent) -> None:
    """Dismiss dialog on Enter or Escape, otherwise skip."""
    key_code = event.GetKeyCode()
    if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_ESCAPE):
        dialog.EndModal(wx.ID_OK)
    else:
        event.Skip()


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
        # Use native background (adapts to Dark Mode)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Message label
        self.label = wx.StaticText(panel, label="Processing...")
        self.label.SetFont(styles.Font.BODY())
        self.label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(self.label, 0, wx.ALL, 20)

        # Progress bar
        self.progress = wx.Gauge(panel, range=total, size=(350, -1))
        sizer.Add(self.progress, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Count label
        self.count_label = wx.StaticText(panel, label=f"0 / {total}")
        self.count_label.SetFont(styles.Font.SMALL())
        self.count_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
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

        sizer.AddSpacer(_DIALOG_PADDING)

        # Header
        header = wx.StaticText(self, label="Rename Plan")
        header.SetFont(styles.Font.TITLE())
        header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(header, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_HEADER_GAP)

        # Summary counts
        ok_count = sum(1 for item in plan if item.status == STATUS_OK)
        dup_count = sum(1 for item in plan if item.status == STATUS_DUPLICATE)
        error_count = sum(1 for item in plan if item.status == STATUS_SKIP_ERROR)
        skip_count = sum(1 for item in plan if item.status.startswith("skip") and item.status != STATUS_SKIP_ERROR)

        # Count unique directories
        directories = {item.old_path.parent for item in plan}

        summary = f"{ok_count} rename(s)"
        if dup_count:
            summary += f", {dup_count} duplicate(s)"
        if skip_count:
            summary += f", {skip_count} skipped"
        if error_count:
            summary += f", {error_count} error(s)"
        if len(directories) > 1:
            summary += f" across {len(directories)} directories"

        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(styles.Font.BODY())
        summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(summary_label, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Status labels and colors
        STATUS_LABELS = {
            STATUS_OK: "OK", STATUS_DUPLICATE: "DUP",
            STATUS_SKIP_NO_NAME: "SKIP", STATUS_SKIP_SAME: "SAME", STATUS_SKIP_ERROR: "ERROR",
        }
        STATUS_COLORS = {
            STATUS_OK: styles.Color.SUCCESS,
            STATUS_DUPLICATE: styles.Color.TEXT_PRIMARY,
            STATUS_SKIP_NO_NAME: styles.Color.TEXT_SECONDARY,
            STATUS_SKIP_SAME: styles.Color.TEXT_SECONDARY,
            STATUS_SKIP_ERROR: styles.Color.ERROR,
        }

        # Show full paths only when multiple directories
        multi_dir = len(directories) > 1

        # Prepare data and colors
        data = []
        colors = []
        for item in plan:
            old_display = _display_path(item.old_path) if multi_dir else item.old_path.name
            if item.status not in (STATUS_SKIP_NO_NAME, STATUS_SKIP_SAME, STATUS_SKIP_ERROR):
                new_display = _display_path(item.new_path) if multi_dir else item.new_path.name
            else:
                new_display = "-"
            status_text = STATUS_LABELS.get(item.status, item.status)
            data.append([old_display, new_display, status_text])
            colors.append(STATUS_COLORS.get(item.status, styles.Color.TEXT_PRIMARY))

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(
            self,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )
        self.list_ctrl.AssociateModel(self.model)

        # Add columns — file name columns share remaining space equally
        col_label = "Original" if multi_dir else "Original File Name"
        new_label = "New" if multi_dir else "New File Name"
        file_col_width = (700 - 2 * _DIALOG_PADDING - _SCROLLBAR_WIDTH - _STATUS_COL_WIDTH) // 2
        self.list_ctrl.AppendTextColumn(col_label, 0, width=file_col_width)
        self.list_ctrl.AppendTextColumn(new_label, 1, width=file_col_width)
        self.list_ctrl.AppendTextColumn("Status", 2, width=_STATUS_COL_WIDTH)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        confirm_btn = wx.Button(self, wx.ID_OK, "Rename All")
        confirm_btn.Bind(wx.EVT_BUTTON, self._on_confirm)
        btn_sizer.Add(confirm_btn, 0, wx.RIGHT, _BTN_GAP)

        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

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

        sizer.AddSpacer(_DIALOG_PADDING)

        # Summary header
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        symbol = wx.StaticText(self, label="\u26A0")
        symbol_font = styles.Font.TITLE()
        symbol_font.SetPointSize(20)
        symbol.SetFont(symbol_font)
        symbol.SetForegroundColour(styles.Color.ERROR)
        header_sizer.Add(symbol, 0, wx.RIGHT, _BTN_GAP)

        summary = f"{len(errors)} error(s)"
        if auth_aborted:
            summary += " — batch aborted"
        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(styles.Font.HEADING())
        summary_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        header_sizer.Add(summary_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(header_sizer, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Prepare data and colors (all errors in red)
        data = [[filename, error_msg] for filename, error_msg in errors]
        colors = [styles.Color.ERROR] * len(errors)

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(
            self,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )
        self.list_ctrl.AssociateModel(self.model)

        # Add columns — split space equally
        col_width = (650 - 2 * _DIALOG_PADDING - _SCROLLBAR_WIDTH) // 2
        self.list_ctrl.AppendTextColumn("File Name", 0, width=col_width)
        self.list_ctrl.AppendTextColumn("Error", 1, width=col_width)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

        # OK button
        ok_btn = wx.Button(self, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(_DIALOG_PADDING)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, lambda e: _dismiss_on_key(self, e))


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

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Header
        header = wx.StaticText(self, label="Rename Complete")
        header.SetFont(styles.Font.TITLE())
        header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(header, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_HEADER_GAP)

        # Summary counts
        summary = f"{renamed} renamed, {skipped} skipped"
        if errors:
            summary += f", {errors} failed"

        summary_label = wx.StaticText(self, label=summary)
        summary_label.SetFont(styles.Font.BODY())
        summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(summary_label, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = [r for r in results if not r.success or r.message == "Renamed"]

        # Show full paths only when multiple directories
        directories = {(r.new_path if r.success else r.old_path).parent for r in results}
        multi_dir = len(directories) > 1

        # Prepare data and colors
        data = []
        colors = []
        for r in visible:
            path = r.new_path if r.success else r.old_path
            display_name = _display_path(path) if multi_dir else path.name
            if r.success:
                result_text = "OK"
                colors.append(styles.Color.SUCCESS)
            else:
                result_text = f"ERROR: {r.message}"
                colors.append(styles.Color.ERROR)
            data.append([display_name, result_text])

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(
            self,
            style=dv.DV_ROW_LINES | dv.DV_VERT_RULES
        )
        self.list_ctrl.AssociateModel(self.model)

        # Add columns
        file_col_width = 650 - 2 * _DIALOG_PADDING - _SCROLLBAR_WIDTH - _RESULT_COL_WIDTH
        self.list_ctrl.AppendTextColumn("File Name", 0, width=file_col_width)
        self.list_ctrl.AppendTextColumn("Result", 1, width=_RESULT_COL_WIDTH)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

        # OK button
        ok_btn = wx.Button(self, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER)

        sizer.AddSpacer(_DIALOG_PADDING)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, lambda e: _dismiss_on_key(self, e))
