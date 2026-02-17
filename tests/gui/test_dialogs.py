"""Tests for wxPython dialog components."""

from pathlib import Path

import pytest
import wx
import wx.dataview as dv
from app.gui.dialogs import (
    _display_path,
    TableModel,
    ProgressDialog,
    RenameConfirmDialog,
    ErrorListDialog,
    CompletionDialog,
)
from app.models.card import RenamePlanItem, RenameResult


# --- _display_path ---

class TestDisplayPath:
    """Tests for _display_path() helper."""

    def test_home_relative(self):
        home = Path.home()
        p = home / "Documents" / "file.pdf"
        result = _display_path(p)
        assert result.startswith("~/")
        assert "Documents/file.pdf" in result

    def test_non_home_path(self):
        p = Path("/tmp/file.pdf")
        result = _display_path(p)
        assert result == "/tmp/file.pdf"


# --- TableModel (pre-existing tests preserved) ---

@pytest.mark.gui
class TestTableModel:
    """Tests for TableModel data view model.

    TableModel provides colored rows for DataViewCtrl tables.
    These tests require wx.App to be initialized.
    """

    def test_initialization(self, wx_app):
        """Should initialize with data and colors."""
        data = [["row1", "value1"], ["row2", "value2"]]
        colors = [wx.Colour(255, 0, 0), wx.Colour(0, 255, 0)]

        model = TableModel(data, colors)

        assert model.data == data
        assert model.colors == colors

    def test_get_column_count_multiple_columns(self, wx_app):
        """Should return correct column count for multi-column data."""
        data = [["col1", "col2", "col3"]]
        colors = [wx.Colour(0, 0, 0)]

        model = TableModel(data, colors)

        assert model.GetColumnCount() == 3

    def test_get_column_count_single_column(self, wx_app):
        """Should return 1 for single column data."""
        data = [["only_col"]]
        colors = [wx.Colour(0, 0, 0)]

        model = TableModel(data, colors)

        assert model.GetColumnCount() == 1

    def test_get_column_count_empty_data(self, wx_app):
        """Should return 0 for empty data."""
        model = TableModel([], [])

        assert model.GetColumnCount() == 0

    def test_get_children_root(self, wx_app):
        """Should return all rows as children of root."""
        data = [["row1"], ["row2"], ["row3"]]
        colors = [wx.Colour(0, 0, 0)] * 3

        model = TableModel(data, colors)
        children = []

        # Pass invalid item (null) for root
        count = model.GetChildren(dv.NullDataViewItem, children)

        assert count == 3
        assert len(children) == 3

    def test_get_children_non_root(self, wx_app):
        """Should return 0 children for non-root items (flat list)."""
        data = [["row1"], ["row2"]]
        colors = [wx.Colour(0, 0, 0)] * 2

        model = TableModel(data, colors)

        # Get a child item first
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        first_item = children[0]

        # Non-root items should have no children
        sub_children = []
        count = model.GetChildren(first_item, sub_children)

        assert count == 0
        assert len(sub_children) == 0

    def test_is_container_root(self, wx_app):
        """Should return True for root (null) item."""
        model = TableModel([["data"]], [wx.Colour(0, 0, 0)])

        # Null item represents root
        assert model.IsContainer(dv.NullDataViewItem) is True

    def test_is_container_regular_item(self, wx_app):
        """Should return False for regular items (flat list)."""
        data = [["row1"]]
        colors = [wx.Colour(0, 0, 0)]

        model = TableModel(data, colors)

        # Get a regular item
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[0]

        assert model.IsContainer(item) is False

    def test_get_parent_always_null(self, wx_app):
        """Should always return null parent (flat list)."""
        data = [["row1"]]
        colors = [wx.Colour(0, 0, 0)]

        model = TableModel(data, colors)

        # Get an item
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[0]

        parent = model.GetParent(item)

        assert not parent.IsOk()  # Null item

    def test_get_value_first_row_first_col(self, wx_app):
        """Should return correct value for row 0, col 0."""
        data = [["A", "B"], ["C", "D"]]
        colors = [wx.Colour(0, 0, 0)] * 2

        model = TableModel(data, colors)

        # Get first item
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[0]

        value = model.GetValue(item, 0)

        assert value == "A"

    def test_get_value_second_row_second_col(self, wx_app):
        """Should return correct value for row 1, col 1."""
        data = [["A", "B"], ["C", "D"]]
        colors = [wx.Colour(0, 0, 0)] * 2

        model = TableModel(data, colors)

        # Get second item
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[1]

        value = model.GetValue(item, 1)

        assert value == "D"

    @pytest.mark.parametrize("row_idx,col_idx,expected", [
        (0, 0, "A"),
        (0, 1, "B"),
        (0, 2, "C"),
        (1, 0, "D"),
        (1, 1, "E"),
        (1, 2, "F"),
        (2, 0, "G"),
        (2, 1, "H"),
        (2, 2, "I"),
    ])
    def test_get_value_various_positions(self, wx_app, row_idx, col_idx, expected):
        """Test GetValue for various row/column combinations."""
        data = [
            ["A", "B", "C"],
            ["D", "E", "F"],
            ["G", "H", "I"],
        ]
        colors = [wx.Colour(0, 0, 0)] * 3

        model = TableModel(data, colors)

        # Get all items
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[row_idx]

        value = model.GetValue(item, col_idx)

        assert value == expected

    def test_get_attr_with_color(self, wx_app):
        """Should set color attribute for row with defined color."""
        red = wx.Colour(255, 0, 0)
        data = [["row1"]]
        colors = [red]

        model = TableModel(data, colors)

        # Get item
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[0]

        # Create attribute object
        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 0, attr)

        assert result is True
        assert attr.GetColour() == red

    def test_get_attr_multiple_rows_different_colors(self, wx_app):
        """Should set correct color for each row."""
        red = wx.Colour(255, 0, 0)
        green = wx.Colour(0, 255, 0)
        blue = wx.Colour(0, 0, 255)

        data = [["row1"], ["row2"], ["row3"]]
        colors = [red, green, blue]

        model = TableModel(data, colors)

        # Get all items
        children = []
        model.GetChildren(dv.NullDataViewItem, children)

        # Test first row - red
        attr1 = dv.DataViewItemAttr()
        result1 = model.GetAttr(children[0], 0, attr1)
        assert result1 is True
        assert attr1.GetColour() == red

        # Test second row - green
        attr2 = dv.DataViewItemAttr()
        result2 = model.GetAttr(children[1], 0, attr2)
        assert result2 is True
        assert attr2.GetColour() == green

        # Test third row - blue
        attr3 = dv.DataViewItemAttr()
        result3 = model.GetAttr(children[2], 0, attr3)
        assert result3 is True
        assert attr3.GetColour() == blue

    def test_get_attr_row_without_color(self, wx_app):
        """Should return False for row index beyond colors list."""
        data = [["row1"], ["row2"]]
        colors = [wx.Colour(255, 0, 0)]  # Only one color for two rows

        model = TableModel(data, colors)

        # Get second item (index 1, no color defined)
        children = []
        model.GetChildren(dv.NullDataViewItem, children)
        item = children[1]

        attr = dv.DataViewItemAttr()
        result = model.GetAttr(item, 0, attr)

        assert result is False

    def test_empty_model(self, wx_app):
        """Should handle empty data gracefully."""
        model = TableModel([], [])

        assert model.GetColumnCount() == 0

        children = []
        count = model.GetChildren(dv.NullDataViewItem, children)
        assert count == 0
        assert len(children) == 0

    def test_single_cell_data(self, wx_app):
        """Should handle single cell data."""
        data = [["single"]]
        colors = [wx.Colour(100, 100, 100)]

        model = TableModel(data, colors)

        assert model.GetColumnCount() == 1

        children = []
        count = model.GetChildren(dv.NullDataViewItem, children)
        assert count == 1

        value = model.GetValue(children[0], 0)
        assert value == "single"

        attr = dv.DataViewItemAttr()
        result = model.GetAttr(children[0], 0, attr)
        assert result is True


# --- ProgressDialog ---

@pytest.mark.gui
class TestProgressDialog:
    """Tests for ProgressDialog."""

    def test_creation(self, wx_app, wx_frame):
        dlg = ProgressDialog(wx_frame, "Processing", 10)
        assert dlg.GetTitle() == "Processing"
        assert dlg._total == 10
        assert dlg._current == 0
        dlg.Destroy()

    def test_update_progress(self, wx_app, wx_frame):
        dlg = ProgressDialog(wx_frame, "Test", 5)
        dlg.update_progress(3, "Working...")
        assert dlg._current == 3
        assert dlg.progress.GetValue() == 3
        assert dlg.label.GetLabel() == "Working..."
        dlg.Destroy()

    def test_update_progress_no_message(self, wx_app, wx_frame):
        dlg = ProgressDialog(wx_frame, "Test", 5)
        dlg.update_progress(2)
        assert dlg._current == 2
        assert dlg.label.GetLabel() == "Processing..."
        dlg.Destroy()

    def test_count_label_format(self, wx_app, wx_frame):
        dlg = ProgressDialog(wx_frame, "Test", 10)
        dlg.update_progress(7)
        assert dlg.count_label.GetLabel() == "7 / 10"
        dlg.Destroy()

    def test_initial_count_label(self, wx_app, wx_frame):
        dlg = ProgressDialog(wx_frame, "Test", 20)
        assert dlg.count_label.GetLabel() == "0 / 20"
        dlg.Destroy()


# --- RenameConfirmDialog ---

@pytest.mark.gui
class TestRenameConfirmDialog:
    """Tests for RenameConfirmDialog."""

    def _make_plan(self, statuses):
        items = []
        for i, status in enumerate(statuses):
            items.append(RenamePlanItem(
                old_path=Path(f"/cards/card{i}.pdf"),
                new_path=Path(f"/cards/Smith Family {i}.pdf"),
                status=status,
            ))
        return items

    def test_creation(self, wx_app, wx_frame):
        plan = self._make_plan(["ok", "skip_no_name"])
        dlg = RenameConfirmDialog(wx_frame, plan, "2025")
        assert dlg.GetTitle() == "Confirm Rename"
        assert dlg.result is False
        dlg.Destroy()

    def test_all_ok(self, wx_app, wx_frame):
        plan = self._make_plan(["ok", "ok", "ok"])
        dlg = RenameConfirmDialog(wx_frame, plan, "2025")
        assert dlg is not None
        dlg.Destroy()

    def test_with_duplicates_and_errors(self, wx_app, wx_frame):
        plan = self._make_plan(["ok", "duplicate", "skip_error", "skip_same"])
        dlg = RenameConfirmDialog(wx_frame, plan, "2025")
        assert dlg is not None
        dlg.Destroy()

    def test_multi_directory(self, wx_app, wx_frame):
        """Plans spanning multiple directories show full paths."""
        plan = [
            RenamePlanItem(Path("/dir1/card1.pdf"), Path("/dir1/Smith.pdf"), "ok"),
            RenamePlanItem(Path("/dir2/card2.pdf"), Path("/dir2/Jones.pdf"), "ok"),
        ]
        dlg = RenameConfirmDialog(wx_frame, plan, "2025")
        assert dlg is not None
        dlg.Destroy()

    def test_single_directory(self, wx_app, wx_frame):
        """Single directory plan shows just filenames."""
        plan = [
            RenamePlanItem(Path("/cards/a.pdf"), Path("/cards/b.pdf"), "ok"),
            RenamePlanItem(Path("/cards/c.pdf"), Path("/cards/d.pdf"), "ok"),
        ]
        dlg = RenameConfirmDialog(wx_frame, plan, "2025")
        assert dlg is not None
        dlg.Destroy()


# --- ErrorListDialog ---

@pytest.mark.gui
class TestErrorListDialog:
    """Tests for ErrorListDialog."""

    def test_creation(self, wx_app, wx_frame):
        errors = [("card1.pdf", "Rate limit"), ("card2.pdf", "Timeout")]
        dlg = ErrorListDialog(wx_frame, "Errors", errors)
        assert dlg.GetTitle() == "Errors"
        dlg.Destroy()

    def test_auth_aborted(self, wx_app, wx_frame):
        errors = [("card1.pdf", "Invalid API key")]
        dlg = ErrorListDialog(wx_frame, "Errors", errors, auth_aborted=True)
        assert dlg is not None
        dlg.Destroy()

    def test_single_error(self, wx_app, wx_frame):
        errors = [("test.pdf", "Connection failed")]
        dlg = ErrorListDialog(wx_frame, "Error", errors)
        assert dlg is not None
        dlg.Destroy()

    def test_many_errors(self, wx_app, wx_frame):
        errors = [(f"card{i}.pdf", f"Error {i}") for i in range(20)]
        dlg = ErrorListDialog(wx_frame, "Errors", errors)
        assert dlg is not None
        dlg.Destroy()


# --- CompletionDialog ---

@pytest.mark.gui
class TestCompletionDialog:
    """Tests for CompletionDialog."""

    def _make_results(self):
        return [
            RenameResult(Path("/cards/card1.pdf"), Path("/cards/Smith Family.pdf"), True, "Renamed"),
            RenameResult(Path("/cards/card2.pdf"), Path("/cards/card2.pdf"), True, "Skipped (same name)"),
            RenameResult(Path("/cards/card3.pdf"), Path("/cards/Jones Family.pdf"), False, "Permission denied"),
        ]

    def test_creation(self, wx_app, wx_frame):
        results = self._make_results()
        dlg = CompletionDialog(wx_frame, "Done", results)
        assert dlg.GetTitle() == "Done"
        dlg.Destroy()

    def test_all_success(self, wx_app, wx_frame):
        results = [RenameResult(Path("/a.pdf"), Path("/b.pdf"), True, "Renamed")]
        dlg = CompletionDialog(wx_frame, "Done", results)
        assert dlg is not None
        dlg.Destroy()

    def test_with_errors(self, wx_app, wx_frame):
        results = self._make_results()
        dlg = CompletionDialog(wx_frame, "Done", results)
        assert dlg is not None
        dlg.Destroy()

    def test_multi_directory(self, wx_app, wx_frame):
        results = [
            RenameResult(Path("/dir1/a.pdf"), Path("/dir1/b.pdf"), True, "Renamed"),
            RenameResult(Path("/dir2/c.pdf"), Path("/dir2/d.pdf"), True, "Renamed"),
        ]
        dlg = CompletionDialog(wx_frame, "Done", results)
        assert dlg is not None
        dlg.Destroy()

    def test_all_skipped(self, wx_app, wx_frame):
        results = [
            RenameResult(Path("/a.pdf"), Path("/a.pdf"), True, "Skipped"),
            RenameResult(Path("/b.pdf"), Path("/b.pdf"), True, "Skipped"),
        ]
        dlg = CompletionDialog(wx_frame, "Done", results)
        assert dlg is not None
        dlg.Destroy()
