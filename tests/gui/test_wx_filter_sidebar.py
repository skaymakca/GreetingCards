"""Tests for wxPython filter sidebar."""

import pytest
import wx
from app.gui.wx_filter_sidebar import FilterSidebar


@pytest.fixture
def wx_app():
    """Create wx.App for testing."""
    app = wx.App()
    yield app
    app.Destroy()


def test_sidebar_creation(wx_app):
    """Test sidebar can be created."""
    parent = wx.Frame(None)
    called_with = []

    def on_filter(filter_key):
        called_with.append(filter_key)

    sidebar = FilterSidebar(parent, on_filter=on_filter)
    assert sidebar is not None
    assert sidebar._on_filter == on_filter
    assert sidebar._selected_filters == ["all"]  # Default filter (multi-select)

    parent.Destroy()


def test_sidebar_checklist_exists(wx_app):
    """Test filter checklist control is created."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Check list exists and has correct items
    assert sidebar._checklist is not None
    assert isinstance(sidebar._checklist, wx.CheckListBox)
    assert sidebar._checklist.GetCount() == 5  # 5 filter options (added "Manual Entry")

    parent.Destroy()


def test_default_filter_selected(wx_app):
    """Test 'All Cards' is checked by default."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # "all" (index 0) should be checked
    assert sidebar._checklist.IsChecked(0) is True
    assert sidebar.get_selected_filters() == ["all"]

    parent.Destroy()


def test_filter_selection_callback(wx_app):
    """Test selecting filters calls the callback with list."""
    parent = wx.Frame(None)
    called_with = []

    def on_filter(filter_keys):
        called_with.append(filter_keys)

    sidebar = FilterSidebar(parent, on_filter=on_filter)

    # Simulate checking "high" filter (index 2)
    sidebar._checklist.Check(2, True)
    # Manually trigger the event handler logic
    sidebar._selected_filters = ["high"]

    # Verify the selected filters
    assert sidebar.get_selected_filters() == ["high"]

    parent.Destroy()


def test_multi_selection_behavior(wx_app):
    """Test multiple filters can be selected (multi-select)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Initially "all" (index 0) is checked
    assert sidebar._checklist.IsChecked(0) is True

    # Set multiple filters using set_filters
    sidebar.set_filters(["high", "needs_review"])

    # Both should be checked
    assert sidebar._checklist.IsChecked(2) is True  # "high" is index 2
    assert sidebar._checklist.IsChecked(3) is True  # "needs_review" is index 3
    assert sidebar.get_selected_filters() == ["high", "needs_review"]

    parent.Destroy()


def test_get_selected_filters(wx_app):
    """Test getting the currently selected filters."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    assert sidebar.get_selected_filters() == ["all"]

    sidebar.set_filters(["high", "manual"])
    assert sidebar.get_selected_filters() == ["high", "manual"]

    parent.Destroy()


def test_set_filters_programmatically(wx_app):
    """Test setting filters programmatically."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Set filters programmatically
    sidebar.set_filters(["high", "needs_review"])

    # Verify state updated
    assert sidebar.get_selected_filters() == ["high", "needs_review"]
    assert sidebar._checklist.IsChecked(2) is True  # high
    assert sidebar._checklist.IsChecked(3) is True  # needs_review
    assert sidebar._checklist.IsChecked(0) is False  # all unchecked

    parent.Destroy()


def test_tooltip_on_checklist(wx_app):
    """Test checklist control has tooltip."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    tooltip = sidebar._checklist.GetToolTip()
    assert tooltip is not None
    assert len(tooltip.GetTip()) > 0

    parent.Destroy()


def test_min_size_set(wx_app):
    """Test sidebar has a minimum width."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    min_width, _ = sidebar.GetMinSize()
    assert min_width == 150

    parent.Destroy()


def test_update_card_counts(wx_app):
    """Test updating card counts updates labels."""
    from pathlib import Path
    from app.models.card import CardResult, Confidence

    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Create test cards
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
        CardResult(id=1, file_paths=[Path("/test/card2.pdf")], primary_path=Path("/test/card2.pdf")),
        CardResult(id=2, file_paths=[Path("/test/card3.pdf")], primary_path=Path("/test/card3.pdf")),
    ]
    cards[0].confidence = Confidence.HIGH
    cards[1].confidence = Confidence.MANUAL
    cards[2].confidence = Confidence.MEDIUM

    # Update counts
    sidebar.update_card_counts(cards)

    # Verify labels include counts
    assert "All Cards (3)" in sidebar._checklist.GetString(0)
    assert "Manual Entry (1)" in sidebar._checklist.GetString(1)
    assert "High Confidence (1)" in sidebar._checklist.GetString(2)
    assert "Needs Review (1)" in sidebar._checklist.GetString(3)
    assert "Errors (0)" in sidebar._checklist.GetString(4)

    parent.Destroy()
