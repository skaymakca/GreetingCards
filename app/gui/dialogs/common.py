"""wxPython dialog classes for the application."""

from pathlib import Path

import wx
import wx.dataview as dv

from app.core.pipeline.ai_analyzer import AIError
from app.gui import styles
from app.gui.rename_display import (
    filter_visible_results,
    format_plan_summary,
    format_result_status,
    format_results_summary,
    get_plan_item_display,
    is_skip_status,
    summarize_plan,
    summarize_results,
)
from app.models.card import RenamePlanItem, RenameResult

# Dialog layout constants
_DIALOG_PADDING = 20  # Outer margin for dialog content
_HEADER_GAP = 4  # Gap between header and summary text
_SECTION_GAP = 12  # Gap between summary and table/content
_BTN_GAP = 8  # Gap between adjacent buttons
_SCROLLBAR_WIDTH = 20  # Reserve space for vertical scrollbar
_STATUS_COL_WIDTH = 100  # Width for short status columns (OK, SKIP, SAME, ERROR, DUP)
_RESULT_COL_WIDTH = 140  # Width for result columns (OK, ERROR: msg)


def display_path(path: Path) -> str:
    """Format a path as ~/relative for display (or just filename if under home)."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


class TableModel(dv.PyDataViewModel):
    """DataViewModel for tables with colored rows."""

    def __init__(self, data: list[list[str]], colors: list[wx.Colour]) -> None:
        """Initialize model.

        Args:
            data: List of lists (rows x columns)
            colors: List of wx.Colour for each row
        """
        super().__init__()
        self.data = data
        self.colors = colors

    # noinspection PyPep8Naming
    def GetColumnCount(self) -> int:
        """Return number of columns."""
        return len(self.data[0]) if self.data else 0

    def GetChildren(self, item: dv.DataViewItem, children: list[dv.DataViewItem]) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Return list of children for parent item."""
        # For a flat list, root has all items as children
        if not item:
            for i in range(len(self.data)):
                children.append(self.ObjectToItem(i))
            return len(self.data)
        return 0

    def IsContainer(self, item: dv.DataViewItem) -> bool:
        """Check if item is a container (has children)."""
        # Only root is a container
        return not item

    def GetParent(self, item: dv.DataViewItem) -> dv.DataViewItem:
        """Return parent of item."""
        # All items have root as parent
        return dv.NullDataViewItem

    def GetValue(self, item: dv.DataViewItem, col: int) -> str:
        """Return value for item and column."""
        row = self.ItemToObject(item)
        return self.data[row][col]

    def GetAttr(self, item: dv.DataViewItem, col: int, attr: dv.DataViewItemAttr) -> bool:
        """Set display attributes for item."""
        row = self.ItemToObject(item)
        if row < len(self.colors):
            attr.SetColour(self.colors[row])
            return True
        return False


def _dismiss_on_key(dialog: wx.Dialog, event: wx.KeyEvent) -> None:
    """Dismiss dialog on Enter or Escape, otherwise skip."""
    key_code = event.GetKeyCode()
    if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
        dialog.EndModal(wx.ID_OK)
    elif key_code == wx.WXK_ESCAPE:
        dialog.EndModal(wx.ID_CANCEL)
    else:
        event.Skip()


# noinspection PyTypeChecker
class ProgressDialog(wx.Dialog):
    """Modal progress dialog for batch processing."""

    def __init__(self, parent: wx.Window, title: str, total: int) -> None:
        super().__init__(
            parent,
            title=title,
            style=wx.CAPTION,  # No close button
        )

        self._total = total
        self._current = 0

        # Create panel
        panel = wx.Panel(self)
        # Use native background (adapts to Dark Mode)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Message label
        self._label = wx.StaticText(panel, label="Processing...")
        self._label.SetFont(styles.Font.BODY())
        self._label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(self._label, 0, wx.ALL, 20)

        # Progress bar
        self._progress = wx.Gauge(panel, range=total, size=(350, -1))
        sizer.Add(self._progress, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # Count label
        self._count_label = wx.StaticText(panel, label=f"0 / {total}")
        self._count_label.SetFont(styles.Font.SMALL())
        self._count_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(self._count_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Set sizers
        panel.SetSizer(sizer)
        sizer.Fit(panel)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        dialog_sizer.Fit(self)

        # Center on parent
        self.CenterOnParent()

        # Prevent closing (Veto the close event so the dialog stays open)
        self.Bind(wx.EVT_CLOSE, lambda evt: evt.Veto())

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        self._label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self._count_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        self.Refresh()

    def update_progress(self, current: int, message: str = "") -> None:
        """Update progress bar and labels.

        Args:
            current: Current progress value
            message: Optional message to display
        """
        self._current = current
        self._progress.SetValue(current)
        self._count_label.SetLabel(f"{current} / {self._total}")
        if message:
            self._label.SetLabel(message)

    def finish(self) -> None:
        """Close the dialog."""
        self.EndModal(wx.ID_OK)
        self.Destroy()


# noinspection PyUnusedLocal,PyTypeChecker
class RenameConfirmDialog(wx.Dialog):
    """Dialog showing the rename plan and asking for confirmation."""

    def __init__(self, parent: wx.Window, plan: list[RenamePlanItem]) -> None:
        super().__init__(
            parent, title="Confirm Rename", size=(700, 500), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.result = False

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Header
        self._header = wx.StaticText(self, label="Rename Plan")
        self._header.SetFont(styles.Font.TITLE())
        self._header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(self._header, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_HEADER_GAP)

        # Summary counts
        counts = summarize_plan(plan)
        summary = format_plan_summary(plan)

        self._summary_label = wx.StaticText(self, label=summary)
        self._summary_label.SetFont(styles.Font.BODY())
        self._summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(self._summary_label, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Category → color mapping (GUI concern)
        _CATEGORY_COLOR: dict[str, wx.Colour] = {
            "ok": styles.Color.SUCCESS,
            "duplicate": styles.Color.TEXT_PRIMARY,
            "skip": styles.Color.TEXT_SECONDARY,
            "error": styles.Color.ERROR,
        }

        # Show full paths only when multiple directories
        multi_dir = counts["directory_count"] > 1

        # Prepare data and colors
        data = []
        colors = []
        for item in plan:
            old_display = display_path(item.old_path) if multi_dir else item.old_path.name
            new_display = (
                "-" if is_skip_status(item) else (display_path(item.new_path) if multi_dir else item.new_path.name)
            )
            label, category = get_plan_item_display(item)
            color = _CATEGORY_COLOR.get(category, styles.Color.TEXT_PRIMARY)
            data.append([old_display, new_display, label])
            colors.append(color)

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(self, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES)
        self.list_ctrl.AssociateModel(self.model)

        # Add columns — file name columns share remaining space equally
        col_label = "Original" if multi_dir else "Original File Name"
        new_label = "New" if multi_dir else "New File Name"
        file_col_width = (700 - 2 * _DIALOG_PADDING - _SCROLLBAR_WIDTH - _STATUS_COL_WIDTH) // 2
        self.list_ctrl.AppendTextColumn(col_label, 0, width=file_col_width)
        self.list_ctrl.AppendTextColumn(new_label, 1, width=file_col_width)
        status_col = self.list_ctrl.AppendTextColumn("Status", 2, width=_STATUS_COL_WIDTH)
        status_col.SetMinWidth(_STATUS_COL_WIDTH)

        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()

        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, _BTN_GAP)

        confirm_btn = wx.Button(self, wx.ID_OK, "Rename All")
        confirm_btn.Bind(wx.EVT_BUTTON, self._on_confirm)
        btn_sizer.Add(confirm_btn, 0)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_DIALOG_PADDING)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        self._header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self._summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        self.Refresh()

    def _on_confirm(self, event: wx.CommandEvent) -> None:
        """Handle Rename All button."""
        self.result = True
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event: wx.CommandEvent) -> None:
        """Handle Cancel button."""
        self.result = False
        self.EndModal(wx.ID_CANCEL)

    def _on_key(self, event: wx.KeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_confirm(event)
        elif key_code == wx.WXK_ESCAPE:
            self._on_cancel(event)
        else:
            event.Skip()


# noinspection PyTypeChecker
class ErrorListDialog(wx.Dialog):
    """Dialog showing AI analysis errors in a structured table."""

    def __init__(self, parent: wx.Window, title: str, errors: list[AIError], auth_aborted: bool = False) -> None:
        super().__init__(parent, title=title, size=(650, 400), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Summary header
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        symbol = wx.StaticText(self, label="\u26a0")
        symbol_font = styles.Font.TITLE()
        symbol_font.SetPointSize(20)
        symbol.SetFont(symbol_font)
        symbol.SetForegroundColour(styles.Color.ERROR)
        header_sizer.Add(symbol, 0, wx.RIGHT, _BTN_GAP)

        summary = f"{len(errors)} error(s)"
        if auth_aborted:
            summary += " \u2014 batch aborted"
        self._summary_label = wx.StaticText(self, label=summary)
        self._summary_label.SetFont(styles.Font.HEADING())
        self._summary_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        header_sizer.Add(self._summary_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(header_sizer, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Prepare data and colors from AIError objects (all errors in red)
        data = [[err.kind.value, err.detail] for err in errors]
        colors = [styles.Color.ERROR] * len(errors)

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(self, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES)
        self.list_ctrl.AssociateModel(self.model)

        # Add columns — type column is narrow, detail gets remaining space
        type_col_width = _STATUS_COL_WIDTH
        detail_col_width = 650 - 2 * _DIALOG_PADDING - _SCROLLBAR_WIDTH - type_col_width
        self.list_ctrl.AppendTextColumn("Type", 0, width=type_col_width)
        self.list_ctrl.AppendTextColumn("Details", 1, width=detail_col_width)

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

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        self._summary_label.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self.Refresh()


# noinspection PyTypeChecker
class CompletionDialog(wx.Dialog):
    """Dialog showing rename results in a structured table."""

    def __init__(self, parent: wx.Window, title: str, results: list[RenameResult]) -> None:
        super().__init__(parent, title=title, size=(650, 420), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # Compute counts
        counts = summarize_results(results)

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(_DIALOG_PADDING)

        # Header
        self._header = wx.StaticText(self, label="Rename Complete")
        self._header.SetFont(styles.Font.TITLE())
        self._header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        sizer.Add(self._header, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_HEADER_GAP)

        # Summary counts
        summary = format_results_summary(results)

        self._summary_label = wx.StaticText(self, label=summary)
        self._summary_label.SetFont(styles.Font.BODY())
        self._summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        sizer.Add(self._summary_label, 0, wx.LEFT | wx.RIGHT, _DIALOG_PADDING)

        sizer.AddSpacer(_SECTION_GAP)

        # Filter to only renamed and error rows (skip rows already shown in confirm dialog)
        visible = filter_visible_results(results)

        # Show full paths only when multiple directories
        multi_dir = counts["directory_count"] > 1

        # Prepare data and colors
        data = []
        colors = []
        for r in visible:
            path = r.new_path if r.success else r.old_path
            display_name = display_path(path) if multi_dir else path.name
            result_text = format_result_status(r)
            colors.append(styles.Color.SUCCESS if r.success else styles.Color.ERROR)
            data.append([display_name, result_text])

        # Create model and ctrl
        self.model = TableModel(data, colors)
        self.list_ctrl = dv.DataViewCtrl(self, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES)
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

    def refresh_colors(self) -> None:
        """Re-apply mode-dependent colors after an appearance change."""
        self._header.SetForegroundColour(styles.Color.TEXT_PRIMARY)
        self._summary_label.SetForegroundColour(styles.Color.TEXT_SECONDARY)
        self.Refresh()
