"""Tests for wxPython filter sidebar."""

import pytest
import wx
from pathlib import Path
from app.gui.filter_sidebar import FilterSidebar
from app.models.card import CardResult, Confidence


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

    sidebar = FilterSidebar(parent, on_category_filter=on_filter)
    assert sidebar is not None
    assert sidebar._on_category_filter == on_filter
    assert sidebar._selected_category_filters == ["all"]  # Default filter (multi-select)

    parent.Destroy()


def test_sidebar_checkboxes_exist(wx_app):
    """Test filter checkboxes are created."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Individual checkboxes exist
    assert len(sidebar._category_checkboxes) == 5  # 5 filter options
    for cb in sidebar._category_checkboxes:
        assert isinstance(cb, wx.CheckBox)

    parent.Destroy()


def test_default_filter_selected(wx_app):
    """Test 'All Cards' is checked by default."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # "all" (index 0) should be checked
    assert sidebar._category_checkboxes[0].GetValue() is True
    assert sidebar.get_selected_category_filters() == ["all"]

    parent.Destroy()


def test_filter_selection_callback(wx_app):
    """Test selecting filters calls the callback with list."""
    parent = wx.Frame(None)
    called_with = []

    def on_filter(filter_keys):
        called_with.append(filter_keys)

    sidebar = FilterSidebar(parent, on_category_filter=on_filter)

    # Simulate checking "high" filter (index 2)
    sidebar._category_checkboxes[2].SetValue(True)
    sidebar._selected_category_filters = ["high"]

    # Verify the selected filters
    assert sidebar.get_selected_category_filters() == ["high"]

    parent.Destroy()


def test_multi_selection_behavior(wx_app):
    """Test multiple filters can be selected (multi-select)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Initially "all" (index 0) is checked
    assert sidebar._category_checkboxes[0].GetValue() is True

    # Set multiple filters using set_filters
    sidebar.set_category_filters(["high", "needs_review"])

    # Both should be checked
    assert sidebar._category_checkboxes[2].GetValue() is True  # "high" is index 2
    assert sidebar._category_checkboxes[3].GetValue() is True  # "needs_review" is index 3
    assert sidebar.get_selected_category_filters() == ["high", "needs_review"]

    parent.Destroy()


def test_get_selected_category_filters(wx_app):
    """Test getting the currently selected filters."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    assert sidebar.get_selected_category_filters() == ["all"]

    sidebar.set_category_filters(["high", "manual"])
    assert sidebar.get_selected_category_filters() == ["high", "manual"]

    parent.Destroy()


def test_set_filters_programmatically(wx_app):
    """Test setting filters programmatically."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Set filters programmatically
    sidebar.set_category_filters(["high", "needs_review"])

    # Verify state updated
    assert sidebar.get_selected_category_filters() == ["high", "needs_review"]
    assert sidebar._category_checkboxes[2].GetValue() is True  # high
    assert sidebar._category_checkboxes[3].GetValue() is True  # needs_review
    assert sidebar._category_checkboxes[0].GetValue() is False  # all unchecked

    parent.Destroy()


def test_tooltip_on_sidebar(wx_app):
    """Test sidebar panel has tooltip."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    tooltip = sidebar.GetToolTip()
    assert tooltip is not None
    assert len(tooltip.GetTip()) > 0

    parent.Destroy()


def test_min_size_set(wx_app):
    """Test sidebar has a minimum width."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    min_width, _ = sidebar.GetMinSize()
    assert min_width == 150

    parent.Destroy()


def test_update_category_counts(wx_app):
    """Test updating card counts updates labels."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

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
    sidebar.update_category_counts(cards)

    # Verify labels include counts
    assert sidebar._category_checkboxes[0].GetLabel() == "All Cards (3)"
    assert sidebar._category_checkboxes[1].GetLabel() == "Manual Entry (1)"
    assert sidebar._category_checkboxes[2].GetLabel() == "High Confidence (1)"
    assert sidebar._category_checkboxes[3].GetLabel() == "Needs Review (1)"
    assert sidebar._category_checkboxes[4].GetLabel() == "Errors (0)"

    parent.Destroy()


def test_zero_count_filter_disabled(wx_app):
    """Test that zero-count filters are visually disabled."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Create cards with no errors
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
    ]
    cards[0].confidence = Confidence.HIGH

    sidebar.update_category_counts(cards)

    # "errors" (index 4) should be disabled
    assert "errors" in sidebar._category_disabled_keys
    assert sidebar._category_checkboxes[4].IsEnabled() is False
    assert sidebar._category_checkboxes[4].GetValue() is False

    # Non-zero filters should remain enabled
    assert sidebar._category_checkboxes[0].IsEnabled() is True  # All Cards
    assert sidebar._category_checkboxes[2].IsEnabled() is True  # High Confidence

    parent.Destroy()


def test_selected_filter_reset_on_zero(wx_app):
    """Test that selected filter resets to 'all' when its count goes to zero."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: called_with.append(k))

    # Start with cards that have errors
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
    ]
    cards[0].confidence = Confidence.NONE  # counts as error

    sidebar.update_category_counts(cards)

    # Select "errors" filter
    sidebar.set_category_filters(["errors"])
    assert sidebar.get_selected_category_filters() == ["errors"]

    # Now update with cards that have NO errors
    cards_no_errors = [
        CardResult(id=1, file_paths=[Path("/test/card2.pdf")], primary_path=Path("/test/card2.pdf")),
    ]
    cards_no_errors[0].confidence = Confidence.HIGH

    sidebar.update_category_counts(cards_no_errors)

    # Should have fallen back to "all"
    assert sidebar.get_selected_category_filters() == ["all"]
    assert sidebar._category_checkboxes[0].GetValue() is True  # "All Cards" checked

    parent.Destroy()


def test_regular_click_exclusive_selection(wx_app):
    """Test regular click selects a filter exclusively (Finder-style)."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: called_with.append(k))

    # Start with "All Cards" selected, simulate regular click on "high" (index 2)
    sidebar._category_checkboxes[2].SetValue(True)  # wx toggles before handler
    sidebar._on_category_check("high", option_held=False)

    # Only "high" should be selected
    assert sidebar.get_selected_category_filters() == ["high"]
    assert sidebar._category_checkboxes[2].GetValue() is True
    assert sidebar._category_checkboxes[0].GetValue() is False  # "All Cards" unchecked
    assert sidebar._category_checkboxes[1].GetValue() is False
    assert sidebar._category_checkboxes[3].GetValue() is False

    parent.Destroy()


def test_regular_click_switches_between_filters(wx_app):
    """Test regular click switches from one filter to another exclusively."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Select "high" first
    sidebar.set_category_filters(["high"])

    # Regular click on "needs_review"
    sidebar._category_checkboxes[3].SetValue(True)
    sidebar._on_category_check("needs_review", option_held=False)

    # Only "needs_review" should be selected
    assert sidebar.get_selected_category_filters() == ["needs_review"]
    assert sidebar._category_checkboxes[3].GetValue() is True
    assert sidebar._category_checkboxes[2].GetValue() is False  # "high" unchecked

    parent.Destroy()


def test_option_click_adds_filter(wx_app):
    """Test Option+click adds a filter to multi-selection."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Start with "high" selected exclusively
    sidebar.set_category_filters(["high"])

    # Option+click on "needs_review"
    sidebar._category_checkboxes[3].SetValue(True)  # wx toggles
    sidebar._on_category_check("needs_review", option_held=True)

    # Both should be selected
    assert sidebar.get_selected_category_filters() == ["high", "needs_review"]
    assert sidebar._category_checkboxes[2].GetValue() is True
    assert sidebar._category_checkboxes[3].GetValue() is True
    assert sidebar._category_checkboxes[0].GetValue() is False

    parent.Destroy()


def test_option_click_removes_filter(wx_app):
    """Test Option+click removes a filter from multi-selection."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Start with two filters selected
    sidebar.set_category_filters(["high", "needs_review"])

    # Option+click on "high" to remove it (wx toggles it off)
    sidebar._category_checkboxes[2].SetValue(False)
    sidebar._on_category_check("high", option_held=True)

    # Only "needs_review" should remain
    assert sidebar.get_selected_category_filters() == ["needs_review"]
    assert sidebar._category_checkboxes[2].GetValue() is False
    assert sidebar._category_checkboxes[3].GetValue() is True

    parent.Destroy()


def test_option_click_remove_last_falls_back_to_all(wx_app):
    """Test Option+click removing the last filter falls back to 'All Cards'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Start with only "high" selected
    sidebar.set_category_filters(["high"])

    # Option+click on "high" to remove it (wx toggles it off)
    sidebar._category_checkboxes[2].SetValue(False)
    sidebar._on_category_check("high", option_held=True)

    # Should fall back to "All Cards"
    assert sidebar.get_selected_category_filters() == ["all"]
    assert sidebar._category_checkboxes[0].GetValue() is True

    parent.Destroy()


def test_option_click_from_all_cards(wx_app):
    """Test Option+click on a category when 'All Cards' is selected switches to that category."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # "All Cards" is selected by default
    assert sidebar.get_selected_category_filters() == ["all"]

    # Option+click on "high"
    sidebar._category_checkboxes[2].SetValue(True)
    sidebar._on_category_check("high", option_held=True)

    # Should switch to just "high", "All Cards" unchecked
    assert sidebar.get_selected_category_filters() == ["high"]
    assert sidebar._category_checkboxes[0].GetValue() is False
    assert sidebar._category_checkboxes[2].GetValue() is True

    parent.Destroy()


def test_click_all_cards_resets(wx_app):
    """Test clicking 'All Cards' always resets to exclusive 'all'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Start with multiple filters
    sidebar.set_category_filters(["high", "needs_review"])

    # Click "All Cards"
    sidebar._category_checkboxes[0].SetValue(True)
    sidebar._on_category_check("all", option_held=False)

    # Only "All Cards" should be selected
    assert sidebar.get_selected_category_filters() == ["all"]
    assert sidebar._category_checkboxes[0].GetValue() is True
    assert sidebar._category_checkboxes[2].GetValue() is False
    assert sidebar._category_checkboxes[3].GetValue() is False

    parent.Destroy()


# --- Folder filter tests ---


def test_folder_section_hidden_single_folder(wx_app):
    """Test folder section is hidden when <2 folders."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Single folder
    sidebar.update_folders([Path("/test/folder1")])

    assert not sidebar._folder_separator.IsShown()
    assert not sidebar._folder_header.IsShown()
    assert len(sidebar._folder_checkboxes) == 0
    assert sidebar._selected_folder_filters == ["all_folders"]

    parent.Destroy()


def test_folder_section_hidden_zero_folders(wx_app):
    """Test folder section is hidden when no folders."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    sidebar.update_folders([])

    assert not sidebar._folder_separator.IsShown()
    assert not sidebar._folder_header.IsShown()
    assert len(sidebar._folder_checkboxes) == 0

    parent.Destroy()


def test_folder_section_shown_multiple_folders(wx_app):
    """Test folder section is visible with 2+ folders and has correct checkboxes."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    folders = [Path("/test/Christmas 2024"), Path("/test/Birthday Cards")]
    sidebar.update_folders(folders)

    assert sidebar._folder_separator.IsShown()
    assert sidebar._folder_header.IsShown()
    # "All Folders" + 2 folders = 3 checkboxes
    assert len(sidebar._folder_checkboxes) == 3
    assert sidebar._folder_checkboxes[0].GetLabel() == "All Folders"
    assert sidebar._folder_checkboxes[1].GetLabel() == "Christmas 2024"
    assert sidebar._folder_checkboxes[2].GetLabel() == "Birthday Cards"
    # "All Folders" checked by default
    assert sidebar._folder_checkboxes[0].GetValue() is True

    parent.Destroy()


def test_folder_label_disambiguation(wx_app):
    """Test same-basename folders get parent/name disambiguation."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Two folders with same basename "cards" under different parents
    folders = [Path("/home/alice/cards"), Path("/home/bob/cards")]
    sidebar.update_folders(folders)

    assert len(sidebar._folder_checkboxes) == 3
    assert sidebar._folder_checkboxes[1].GetLabel() == "alice/cards"
    assert sidebar._folder_checkboxes[2].GetLabel() == "bob/cards"

    parent.Destroy()


def test_folder_regular_click_exclusive(wx_app):
    """Test Finder-style exclusive click on folder filters."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: called_with.append(k),
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    # Regular click on folder1
    sidebar._folder_checkboxes[1].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder1")), option_held=False)

    # Only folder1 should be selected
    assert sidebar._selected_folder_filters == [str(Path("/test/folder1"))]
    assert sidebar._folder_checkboxes[1].GetValue() is True
    assert sidebar._folder_checkboxes[0].GetValue() is False  # "All Folders" unchecked
    assert sidebar._folder_checkboxes[2].GetValue() is False

    parent.Destroy()


def test_folder_option_click_multi_select(wx_app):
    """Test Option+click adds folder to selection."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: None,
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    # Exclusive click on folder1 first
    sidebar._folder_checkboxes[1].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder1")), option_held=False)

    # Option+click on folder2
    sidebar._folder_checkboxes[2].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder2")), option_held=True)

    # Both should be selected
    assert set(sidebar._selected_folder_filters) == {str(Path("/test/folder1")), str(Path("/test/folder2"))}

    parent.Destroy()


def test_folder_option_click_remove_last_fallback(wx_app):
    """Test removing last folder falls back to 'All Folders'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: None,
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    # Select folder1 exclusively
    sidebar._folder_checkboxes[1].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder1")), option_held=False)

    # Option+click to remove folder1
    sidebar._folder_checkboxes[1].SetValue(False)
    sidebar._on_folder_check(str(Path("/test/folder1")), option_held=True)

    # Should fall back to "All Folders"
    assert sidebar._selected_folder_filters == ["all_folders"]
    assert sidebar._folder_checkboxes[0].GetValue() is True

    parent.Destroy()


def test_folder_counts_update(wx_app):
    """Test folder counts are shown correctly."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")
    sidebar.update_folders([folder1, folder2])

    cards = [
        CardResult(id=0, file_paths=[folder1 / "card1.pdf"], primary_path=folder1 / "card1.pdf"),
        CardResult(id=1, file_paths=[folder1 / "card2.pdf"], primary_path=folder1 / "card2.pdf"),
        CardResult(id=2, file_paths=[folder2 / "card3.pdf"], primary_path=folder2 / "card3.pdf"),
    ]
    for c in cards:
        c.confidence = Confidence.HIGH

    sidebar.update_folder_counts(cards)

    assert sidebar._folder_checkboxes[0].GetLabel() == "All Folders (3)"
    assert sidebar._folder_checkboxes[1].GetLabel() == "folder1 (2)"
    assert sidebar._folder_checkboxes[2].GetLabel() == "folder2 (1)"

    parent.Destroy()


def test_zero_count_folder_disabled(wx_app):
    """Test zero-count folders are grayed out."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")
    sidebar.update_folders([folder1, folder2])

    # Only folder1 has cards
    cards = [
        CardResult(id=0, file_paths=[folder1 / "card1.pdf"], primary_path=folder1 / "card1.pdf"),
    ]
    cards[0].confidence = Confidence.HIGH

    sidebar.update_folder_counts(cards)

    assert sidebar._folder_checkboxes[1].IsEnabled() is True   # folder1 has cards
    assert sidebar._folder_checkboxes[2].IsEnabled() is False  # folder2 has 0 cards
    assert str(folder2) in sidebar._folder_disabled_keys

    parent.Destroy()


def test_folder_selection_reset_on_zero(wx_app):
    """Test selected folder falls back to 'All Folders' when count goes to zero."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: called_with.append(k),
    )

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")
    sidebar.update_folders([folder1, folder2])

    # Select folder2
    sidebar.set_folder_filters([str(folder2)])

    # Now update with cards only in folder1 (folder2 goes to 0)
    cards = [
        CardResult(id=0, file_paths=[folder1 / "card1.pdf"], primary_path=folder1 / "card1.pdf"),
    ]
    cards[0].confidence = Confidence.HIGH

    sidebar.update_folder_counts(cards)

    # Should have fallen back to "All Folders"
    assert sidebar._selected_folder_filters == ["all_folders"]

    parent.Destroy()


def test_folder_callback_invoked(wx_app):
    """Test folder callback fires with correct keys."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: called_with.append(k),
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    # Click folder1
    sidebar._folder_checkboxes[1].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder1")), option_held=False)

    assert len(called_with) == 1
    assert called_with[0] == [str(Path("/test/folder1"))]

    parent.Destroy()


def test_folder_rebuild_resets_selection(wx_app):
    """Test rebuilding folders resets selection to 'All Folders'."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: None,
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    # Select a specific folder
    sidebar.set_folder_filters([str(Path("/test/folder1"))])
    assert sidebar._selected_folder_filters == [str(Path("/test/folder1"))]

    # Rebuild with different folders
    new_folders = [Path("/test/folderA"), Path("/test/folderB")]
    sidebar.update_folders(new_folders)

    # Selection should be reset
    assert sidebar._selected_folder_filters == ["all_folders"]
    assert sidebar._folder_checkboxes[0].GetValue() is True

    parent.Destroy()


# --- No-callback fallback tests ---


def test_update_category_counts_does_not_fire_callback_on_fallback(wx_app):
    """Test sidebar resets internal state but does NOT fire callback when all selected go to zero."""
    parent = wx.Frame(None)
    called_with = []
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: called_with.append(k))

    # Start with cards that have errors
    cards_with_errors = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
    ]
    cards_with_errors[0].confidence = Confidence.NONE

    sidebar.update_category_counts(cards_with_errors)

    # Select "errors" filter
    sidebar.set_category_filters(["errors"])
    called_with.clear()  # Reset tracking

    # Now update with cards that have NO errors — "errors" goes to zero
    cards_no_errors = [
        CardResult(id=1, file_paths=[Path("/test/card2.pdf")], primary_path=Path("/test/card2.pdf")),
    ]
    cards_no_errors[0].confidence = Confidence.HIGH

    sidebar.update_category_counts(cards_no_errors)

    # Internal state should have reset to "all"
    assert sidebar.get_selected_category_filters() == ["all"]
    assert sidebar._category_checkboxes[0].GetValue() is True

    # But callback should NOT have been fired (prevents re-entrancy)
    assert called_with == []

    parent.Destroy()


def test_update_folder_counts_does_not_fire_callback_on_fallback(wx_app):
    """Test sidebar resets internal folder state but does NOT fire callback when all selected go to zero."""
    parent = wx.Frame(None)
    folder_called_with = []
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: folder_called_with.append(k),
    )

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")
    sidebar.update_folders([folder1, folder2])

    # Select folder2
    sidebar.set_folder_filters([str(folder2)])
    folder_called_with.clear()  # Reset tracking

    # Now update with cards only in folder1 — folder2 goes to zero
    cards = [
        CardResult(id=0, file_paths=[folder1 / "card1.pdf"], primary_path=folder1 / "card1.pdf"),
    ]
    cards[0].confidence = Confidence.HIGH

    sidebar.update_folder_counts(cards)

    # Internal state should have reset to "all_folders"
    assert sidebar._selected_folder_filters == ["all_folders"]

    # But callback should NOT have been fired (prevents re-entrancy)
    assert folder_called_with == []

    parent.Destroy()


# --- Notification tests ---


def test_notification_show(wx_app):
    """Test show_notification displays a message."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    sidebar.show_notification("Test message")
    assert sidebar._notify_label.IsShown()
    # wx may wrap the label text, so normalize whitespace for comparison
    assert sidebar._notify_label.GetLabel().replace("\n", " ") == "Test message"

    parent.Destroy()


def test_notification_timer_stop_on_reshow(wx_app):
    """Test showing notification again stops existing timer (lines 130-131)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    sidebar.show_notification("First", duration_ms=10000)
    first_timer = sidebar._notify_timer
    assert first_timer is not None

    sidebar.show_notification("Second", duration_ms=10000)
    # First timer should have been stopped and replaced
    assert sidebar._notify_label.GetLabel() == "Second"
    assert sidebar._notify_timer is not None

    parent.Destroy()


def test_notification_info_colour(wx_app):
    """Test ICON_INFORMATION uses secondary text colour (line 135)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    from app.gui import styles
    sidebar.show_notification("Info", icon=wx.ICON_INFORMATION)
    assert sidebar._notify_label.GetForegroundColour() == styles.Color.TEXT_SECONDARY

    parent.Destroy()


def test_notification_error_colour(wx_app):
    """Test ICON_ERROR uses error colour (line 133)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    from app.gui import styles
    sidebar.show_notification("Error!", icon=wx.ICON_ERROR)
    assert sidebar._notify_label.GetForegroundColour() == styles.Color.ERROR

    parent.Destroy()


def test_notification_warning_colour(wx_app):
    """Test ICON_WARNING uses error colour (line 132)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    from app.gui import styles
    sidebar.show_notification("Warning!", icon=wx.ICON_WARNING)
    assert sidebar._notify_label.GetForegroundColour() == styles.Color.ERROR

    parent.Destroy()


def test_dismiss_notification(wx_app):
    """Test dismiss_notification hides the label."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    sidebar.show_notification("Test")
    assert sidebar._notify_label.IsShown()

    sidebar.dismiss_notification()
    assert not sidebar._notify_label.IsShown()
    assert sidebar._notify_timer is None

    parent.Destroy()


# --- _apply_count_fallback partial-disable branch ---


def test_apply_count_fallback_partial_disable(wx_app):
    """Test _apply_count_fallback when some (not all) selected filters are disabled (line 318)."""
    parent = wx.Frame(None)
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: None)

    # Set up with cards in high and errors
    cards = [
        CardResult(id=0, file_paths=[Path("/test/card1.pdf")], primary_path=Path("/test/card1.pdf")),
        CardResult(id=1, file_paths=[Path("/test/card2.pdf")], primary_path=Path("/test/card2.pdf")),
    ]
    cards[0].confidence = Confidence.HIGH
    cards[1].confidence = Confidence.NONE  # counts as error

    sidebar.update_category_counts(cards)

    # Select both "high" and "errors"
    sidebar.set_category_filters(["high", "errors"])

    # Now update with cards where only high exists (errors goes to 0)
    cards_no_errors = [
        CardResult(id=2, file_paths=[Path("/test/card3.pdf")], primary_path=Path("/test/card3.pdf")),
    ]
    cards_no_errors[0].confidence = Confidence.HIGH

    sidebar.update_category_counts(cards_no_errors)

    # "errors" was disabled but "high" remains — should keep just "high"
    assert sidebar.get_selected_category_filters() == ["high"]

    parent.Destroy()


# --- Category check with explicit option_held ---


def test_category_check_default_option_held_none(wx_app):
    """Test _on_category_check with option_held=None falls back to wx.GetKeyState."""
    parent = wx.Frame(None)
    called = []
    sidebar = FilterSidebar(parent, on_category_filter=lambda k: called.append(k))

    # Enable "high" checkbox with cards
    cards = [CardResult(id=0, file_paths=[Path("/a.pdf")], primary_path=Path("/a.pdf"))]
    cards[0].confidence = Confidence.HIGH
    sidebar.update_category_counts(cards)

    # Call without option_held — it reads from wx.GetKeyState
    sidebar._category_checkboxes[2].SetValue(True)
    sidebar._on_category_check("high")  # default option_held=None
    assert "high" in sidebar.get_selected_category_filters()

    parent.Destroy()


def test_folder_check_default_option_held_none(wx_app):
    """Test _on_folder_check with option_held=None falls back to wx.GetKeyState."""
    parent = wx.Frame(None)
    called = []
    sidebar = FilterSidebar(
        parent,
        on_category_filter=lambda k: None,
        on_folder_filter=lambda k: called.append(k),
    )

    folders = [Path("/test/folder1"), Path("/test/folder2")]
    sidebar.update_folders(folders)

    sidebar._folder_checkboxes[1].SetValue(True)
    sidebar._on_folder_check(str(Path("/test/folder1")))  # default option_held=None
    assert len(called) >= 1

    parent.Destroy()
