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


def test_sidebar_checkboxes_exist(wx_app):
    """Test filter checkboxes are created."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Individual checkboxes exist
    assert len(sidebar._checkboxes) == 5  # 5 filter options
    for cb in sidebar._checkboxes:
        assert isinstance(cb, wx.CheckBox)

    parent.Destroy()


def test_default_filter_selected(wx_app):
    """Test 'All Cards' is checked by default."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # "all" (index 0) should be checked
    assert sidebar._checkboxes[0].GetValue() is True
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
    sidebar._checkboxes[2].SetValue(True)
    sidebar._selected_filters = ["high"]

    # Verify the selected filters
    assert sidebar.get_selected_filters() == ["high"]

    parent.Destroy()


def test_multi_selection_behavior(wx_app):
    """Test multiple filters can be selected (multi-select)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Initially "all" (index 0) is checked
    assert sidebar._checkboxes[0].GetValue() is True

    # Set multiple filters using set_filters
    sidebar.set_filters(["high", "needs_review"])

    # Both should be checked
    assert sidebar._checkboxes[2].GetValue() is True  # "high" is index 2
    assert sidebar._checkboxes[3].GetValue() is True  # "needs_review" is index 3
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
    assert sidebar._checkboxes[2].GetValue() is True  # high
    assert sidebar._checkboxes[3].GetValue() is True  # needs_review
    assert sidebar._checkboxes[0].GetValue() is False  # all unchecked

    parent.Destroy()


def test_tooltip_on_sidebar(wx_app):
    """Test sidebar panel has tooltip."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    tooltip = sidebar.GetToolTip()
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
    assert sidebar._checkboxes[0].GetLabel() == "All Cards (3)"
    assert sidebar._checkboxes[1].GetLabel() == "Manual Entry (1)"
    assert sidebar._checkboxes[2].GetLabel() == "High Confidence (1)"
    assert sidebar._checkboxes[3].GetLabel() == "Needs Review (1)"
    assert sidebar._checkboxes[4].GetLabel() == "Errors (0)"

    parent.Destroy()


def test_zero_count_filter_disabled(wx_app):
    """Test that zero-count filters are visually disabled."""
    from pathlib import Path
    from app.models.card import CardResult, Confidence

    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Create cards with no errors
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
    ]
    cards[0].confidence = Confidence.HIGH

    sidebar.update_card_counts(cards)

    # "errors" (index 4) should be disabled
    assert "errors" in sidebar._disabled_keys
    assert sidebar._checkboxes[4].IsEnabled() is False
    assert sidebar._checkboxes[4].GetValue() is False

    # Non-zero filters should remain enabled
    assert sidebar._checkboxes[0].IsEnabled() is True  # All Cards
    assert sidebar._checkboxes[2].IsEnabled() is True  # High Confidence

    parent.Destroy()


def test_selected_filter_reset_on_zero(wx_app):
    """Test that selected filter resets to 'all' when its count goes to zero."""
    from pathlib import Path
    from app.models.card import CardResult, Confidence

    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(parent, on_filter=lambda k: called_with.append(k))

    # Start with cards that have errors
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
    ]
    cards[0].confidence = Confidence.NONE  # counts as error

    sidebar.update_card_counts(cards)

    # Select "errors" filter
    sidebar.set_filters(["errors"])
    assert sidebar.get_selected_filters() == ["errors"]

    # Now update with cards that have NO errors
    cards_no_errors = [
        CardResult(id=1, file_paths=[Path("/test/card2.pdf")], primary_path=Path("/test/card2.pdf")),
    ]
    cards_no_errors[0].confidence = Confidence.HIGH

    sidebar.update_card_counts(cards_no_errors)

    # Should have fallen back to "all"
    assert sidebar.get_selected_filters() == ["all"]
    assert sidebar._checkboxes[0].GetValue() is True  # "All Cards" checked

    parent.Destroy()


def test_regular_click_exclusive_selection(wx_app):
    """Test regular click selects a filter exclusively (Finder-style)."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(parent, on_filter=lambda k: called_with.append(k))

    # Start with "All Cards" selected, simulate regular click on "high" (index 2)
    sidebar._checkboxes[2].SetValue(True)  # wx toggles before handler
    sidebar._on_check_change_key("high", option_held=False)

    # Only "high" should be selected
    assert sidebar.get_selected_filters() == ["high"]
    assert sidebar._checkboxes[2].GetValue() is True
    assert sidebar._checkboxes[0].GetValue() is False  # "All Cards" unchecked
    assert sidebar._checkboxes[1].GetValue() is False
    assert sidebar._checkboxes[3].GetValue() is False

    parent.Destroy()


def test_regular_click_switches_between_filters(wx_app):
    """Test regular click switches from one filter to another exclusively."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Select "high" first
    sidebar.set_filters(["high"])

    # Regular click on "needs_review"
    sidebar._checkboxes[3].SetValue(True)
    sidebar._on_check_change_key("needs_review", option_held=False)

    # Only "needs_review" should be selected
    assert sidebar.get_selected_filters() == ["needs_review"]
    assert sidebar._checkboxes[3].GetValue() is True
    assert sidebar._checkboxes[2].GetValue() is False  # "high" unchecked

    parent.Destroy()


def test_option_click_adds_filter(wx_app):
    """Test Option+click adds a filter to multi-selection."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Start with "high" selected exclusively
    sidebar.set_filters(["high"])

    # Option+click on "needs_review"
    sidebar._checkboxes[3].SetValue(True)  # wx toggles
    sidebar._on_check_change_key("needs_review", option_held=True)

    # Both should be selected
    assert sidebar.get_selected_filters() == ["high", "needs_review"]
    assert sidebar._checkboxes[2].GetValue() is True
    assert sidebar._checkboxes[3].GetValue() is True
    assert sidebar._checkboxes[0].GetValue() is False

    parent.Destroy()


def test_option_click_removes_filter(wx_app):
    """Test Option+click removes a filter from multi-selection."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Start with two filters selected
    sidebar.set_filters(["high", "needs_review"])

    # Option+click on "high" to remove it (wx toggles it off)
    sidebar._checkboxes[2].SetValue(False)
    sidebar._on_check_change_key("high", option_held=True)

    # Only "needs_review" should remain
    assert sidebar.get_selected_filters() == ["needs_review"]
    assert sidebar._checkboxes[2].GetValue() is False
    assert sidebar._checkboxes[3].GetValue() is True

    parent.Destroy()


def test_option_click_remove_last_falls_back_to_all(wx_app):
    """Test Option+click removing the last filter falls back to 'All Cards'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Start with only "high" selected
    sidebar.set_filters(["high"])

    # Option+click on "high" to remove it (wx toggles it off)
    sidebar._checkboxes[2].SetValue(False)
    sidebar._on_check_change_key("high", option_held=True)

    # Should fall back to "All Cards"
    assert sidebar.get_selected_filters() == ["all"]
    assert sidebar._checkboxes[0].GetValue() is True

    parent.Destroy()


def test_option_click_from_all_cards(wx_app):
    """Test Option+click on a category when 'All Cards' is selected switches to that category."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # "All Cards" is selected by default
    assert sidebar.get_selected_filters() == ["all"]

    # Option+click on "high"
    sidebar._checkboxes[2].SetValue(True)
    sidebar._on_check_change_key("high", option_held=True)

    # Should switch to just "high", "All Cards" unchecked
    assert sidebar.get_selected_filters() == ["high"]
    assert sidebar._checkboxes[0].GetValue() is False
    assert sidebar._checkboxes[2].GetValue() is True

    parent.Destroy()


def test_click_all_cards_resets(wx_app):
    """Test clicking 'All Cards' always resets to exclusive 'all'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_filter=lambda k: None)

    # Start with multiple filters
    sidebar.set_filters(["high", "needs_review"])

    # Click "All Cards"
    sidebar._checkboxes[0].SetValue(True)
    sidebar._on_check_change_key("all", option_held=False)

    # Only "All Cards" should be selected
    assert sidebar.get_selected_filters() == ["all"]
    assert sidebar._checkboxes[0].GetValue() is True
    assert sidebar._checkboxes[2].GetValue() is False
    assert sidebar._checkboxes[3].GetValue() is False

    parent.Destroy()
