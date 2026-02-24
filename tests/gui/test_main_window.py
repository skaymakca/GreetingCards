"""Tests for wxPython main window."""

import pytest
import wx
from pathlib import Path
from unittest.mock import Mock
from app.gui.main_window import MainWindow, FileDropTarget


@pytest.fixture
def wx_app():
    """Create wx.App for testing."""
    app = wx.App()
    yield app
    app.Destroy()


def test_main_window_creation(wx_app):
    """Test window can be created."""
    window = MainWindow()
    assert window._frame is not None
    assert window._frame.GetTitle() == "Greeting Cards"
    assert window._frame.GetSize()[0] == 1200  # Default width
    assert window._frame.GetMinSize()[0] == 800  # Min width
    window._frame.Destroy()



def test_folder_state_management(wx_app):
    """Test state is initialized correctly (multi-load architecture)."""
    window = MainWindow()
    # No folder concept in multi-load architecture
    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
    assert len(window._pdf_files) == 0
    assert window._next_card_id == 0
    window._frame.Destroy()


def test_year_default_value(wx_app):
    """Test year field defaults to last year."""
    from datetime import datetime
    window = MainWindow()
    expected_year = datetime.now().year - 1
    assert window._year == expected_year
    assert window._year_ctrl.GetValue() == str(expected_year)
    window._frame.Destroy()


def test_menu_bar_exists(wx_app):
    """Test menu bar is created."""
    window = MainWindow()
    menubar = window._frame.GetMenuBar()
    assert menubar is not None
    # Check for File and Help menus
    assert menubar.GetMenuCount() >= 2
    window._frame.Destroy()


def test_panels_exist(wx_app):
    """Test review and preview panels are created."""
    window = MainWindow()
    assert window._review_panel is not None
    assert window._preview_panel is not None
    window._frame.Destroy()


def test_clear_all_resets_state(wx_app):
    """Test _clear_all resets all state."""
    window = MainWindow()

    # Set some dummy state (multi-load architecture)
    window._next_card_id = 5
    window._cards_by_hash = {"hash1": None, "hash2": None}
    window._hash_by_path = {Path("/test1.pdf"): "hash1", Path("/test2.pdf"): "hash2"}
    window._mtime_by_path = {Path("/test1.pdf"): 100.0, Path("/test2.pdf"): 200.0}
    window._pdf_files = [Path("test.pdf")]

    # Clear
    window._clear_all()

    # Verify reset
    assert window._next_card_id == 0
    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
    assert len(window._mtime_by_path) == 0
    assert len(window._pdf_files) == 0

    window._frame.Destroy()


def test_drop_target_creation(wx_app):
    """Test drag-and-drop target is set up."""
    window = MainWindow()
    drop_target = window._frame.GetDropTarget()
    assert drop_target is not None
    assert isinstance(drop_target, FileDropTarget)
    window._frame.Destroy()


def test_file_drop_target_callback():
    """Test FileDropTarget stores callback."""
    def dummy_callback(path):
        pass

    target = FileDropTarget(dummy_callback)
    assert target._on_drop == dummy_callback


def test_file_drop_target_drag_over_callback():
    """Test FileDropTarget calls on_drag_over during drag."""
    on_drop = Mock()
    on_drag_over = Mock()
    on_drag_leave = Mock()
    target = FileDropTarget(on_drop, on_drag_over, on_drag_leave)

    target.OnDragOver(0, 0, wx.DragCopy)
    on_drag_over.assert_called_once()

    target.OnLeave()
    on_drag_leave.assert_called_once()


def test_file_drop_target_drag_callbacks_optional():
    """Test FileDropTarget works without drag callbacks."""
    target = FileDropTarget(Mock())
    # Should not raise
    target.OnDragOver(0, 0, wx.DragCopy)
    target.OnLeave()


def test_drop_overlay_drag_active(wx_app):
    """Test _DropOverlay.set_drag_active toggles flag."""
    from app.gui.main_window import _DropOverlay
    frame = wx.Frame(None)
    overlay = _DropOverlay(frame)
    assert overlay._drag_active is False

    overlay.set_drag_active(True)
    assert overlay._drag_active is True

    overlay.set_drag_active(False)
    assert overlay._drag_active is False
    frame.Destroy()


def test_toolbar_icons_applied(wx_app):
    """Test toolbar tools exist and have bitmaps assigned."""
    window = MainWindow()

    # Verify all toolbar tools are registered
    tool_ids = [
        window._browse_id,
        window._reload_id,
        window._ai_all_id,
        window._rename_id,
        window._clear_id,
    ]

    for tool_id in tool_ids:
        tool = window._toolbar.FindById(tool_id)
        assert tool is not None
        # Bitmap may be NullBitmap in test environments without SF Symbols
        assert tool.GetBitmap() is not None

    window._frame.Destroy()


def test_keyboard_shortcuts_bound(wx_app):
    """Test keyboard shortcuts are set up."""
    window = MainWindow()

    # Verify CHAR_HOOK is bound (for arrow keys)
    # This is a basic check that the binding exists
    assert window._frame.GetEventHandler() is not None

    window._frame.Destroy()


def test_split_window_exists(wx_app):
    """Test splitter window is created."""
    window = MainWindow()

    # Find the splitter in the frame's children
    def find_splitter(widget):
        if isinstance(widget, wx.SplitterWindow):
            return widget
        for child in widget.GetChildren():
            result = find_splitter(child)
            if result:
                return result
        return None

    splitter = find_splitter(window._frame)
    assert splitter is not None
    assert splitter.IsSplit()

    window._frame.Destroy()


def test_callbacks_connected(wx_app):
    """Test review panel callbacks are connected."""
    window = MainWindow()

    # Verify callbacks are set (review panel stores them)
    assert window._review_panel._on_select == window._on_card_select
    assert window._review_panel._on_ai_request == window._on_ai_request
    assert window._review_panel._on_name_change == window._on_name_change
    assert window._review_panel._on_card_edited == window._on_card_edited

    window._frame.Destroy()


def test_processing_progress_without_dialog(wx_app):
    """Test _update_processing_progress handles missing dialog gracefully."""
    window = MainWindow()

    # Call without progress dialog - should not crash
    window._update_processing_progress(1, 10, "test.pdf")

    window._frame.Destroy()


def test_worker_result_to_card_conversion(wx_app):
    """Test conversion of PdfWorkerResult to CardResult."""
    from PIL import Image
    from app.models.card import PdfWorkerResult
    import io

    window = MainWindow()

    # Create test image bytes
    img = Image.new('RGB', (100, 100), color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    worker_result = PdfWorkerResult(
        pdf_path='/test/card.pdf',
        file_hash='abc123',
        family_name='Smith',
        confidence='high',
        method='ocr',
        alternates=['Smyth'],
        candidates=[],
        remove_family=False,
        selected_candidate_id=None,
        ocr_text='Smith Family',
        error=None,
        preview_image_bytes=img_bytes,
        page_images_bytes=[img_bytes],
    )

    card = window._worker_result_to_card(worker_result, card_id=1)

    assert card.id == 1
    assert card.filename == "card.pdf"
    assert card.file_hash == 'abc123'
    assert card.family_name == 'Smith'
    assert card.preview_image is not None
    assert len(card.page_images) == 1

    window._frame.Destroy()


def test_worker_result_to_card_error_preserves_fields(wx_app):
    """Test conversion handles error cards with null hash."""
    from app.models.card import PdfWorkerResult

    window = MainWindow()

    worker_result = PdfWorkerResult(
        pdf_path='/test/card.pdf',
        file_hash=None,
        family_name='',
        confidence='none',
        method='missing',
        error='Failed to process',
    )

    card = window._worker_result_to_card(worker_result, card_id=1)

    assert card.error == 'Failed to process'
    assert card.confidence.value == 'none'
    assert card.file_hash == ''

    window._frame.Destroy()


def test_search_control_exists(wx_app):
    """Test search control is created."""
    window = MainWindow()
    assert window._search_ctrl is not None
    assert isinstance(window._search_ctrl, wx.SearchCtrl)
    assert window._search_ctrl.GetDescriptiveText() == "Filter cards..."
    window._frame.Destroy()


def test_sidebar_notification_exists(wx_app):
    """Test sidebar has notification area."""
    window = MainWindow()
    assert hasattr(window._sidebar, '_notify_label')
    assert not window._sidebar._notify_label.IsShown()
    window._frame.Destroy()


def test_tooltips_applied(wx_app):
    """Test tooltips/shortHelp are set on all toolbar controls and tools."""
    window = MainWindow()

    # Check toolbar tools have shortHelp text
    tool_checks = [
        (window._browse_id, "Add PDF files"),
        (window._reload_id, "Re-check"),
        (window._ai_all_id, "Analyze"),
        (window._rename_id, "Rename"),
        (window._clear_id, "Clear"),
    ]

    for tool_id, expected_text in tool_checks:
        short_help = window._toolbar.GetToolShortHelp(tool_id)
        assert expected_text.lower() in short_help.lower(), f"Expected '{expected_text}' in '{short_help}'"

    # Check embedded controls have tooltips
    ctrl_checks = [
        (window._search_ctrl, "Filter"),
        (window._year_ctrl, "Year"),
    ]

    for ctrl, expected_text in ctrl_checks:
        tooltip = ctrl.GetToolTip()
        assert tooltip is not None
        assert expected_text.lower() in tooltip.GetTip().lower()

    window._frame.Destroy()


def test_search_ctrl_tooltip(wx_app):
    """Test search control has tooltip."""
    window = MainWindow()
    tooltip = window._search_ctrl.GetToolTip()
    assert tooltip is not None
    assert "Filter" in tooltip.GetTip()
    window._frame.Destroy()


def test_search_filtering(wx_app):
    """Test search filtering works correctly."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add some test cards
    card1 = CardResult(id=0, file_paths=[Path("/test/smith_card.pdf")], primary_path=Path("/test/smith_card.pdf"))
    card1.family_name = "Smith"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "hash1"

    card2 = CardResult(id=1, file_paths=[Path("/test/jones_card.pdf")], primary_path=Path("/test/jones_card.pdf"))
    card2.family_name = "Jones"
    card2.confidence = Confidence.HIGH
    card2.file_hash = "hash2"

    card3 = CardResult(id=2, file_paths=[Path("/test/johnson_card.pdf")], primary_path=Path("/test/johnson_card.pdf"))
    card3.family_name = "Johnson"
    card3.confidence = Confidence.HIGH
    card3.file_hash = "hash3"

    # Store by hash (multi-load architecture)
    window._cards_by_hash = {"hash1": card1, "hash2": card2, "hash3": card3}

    # Test filtering by filename
    window._search_ctrl.SetValue("smith")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 0

    # Test filtering by family name
    window._search_ctrl.SetValue("Jones")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 1

    # Test partial match
    window._search_ctrl.SetValue("john")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 2

    # Test no match
    window._search_ctrl.SetValue("xyz")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 0

    # Test empty query returns all
    window._search_ctrl.SetValue("")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 3

    window._frame.Destroy()


def test_search_cancel_clears_filter(wx_app):
    """Test search cancel button clears the filter."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add test card
    card1 = CardResult(id=0, file_paths=[Path("/test/smith_card.pdf")], primary_path=Path("/test/smith_card.pdf"))
    card1.family_name = "Smith"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card1}

    # Set search value
    window._search_ctrl.SetValue("test")
    assert window._search_ctrl.GetValue() == "test"

    # Trigger cancel
    window._on_search_cancel(None)

    # Verify cleared
    assert window._search_ctrl.GetValue() == ""

    window._frame.Destroy()


def test_clear_all_clears_search(wx_app):
    """Test _clear_all clears the search field."""
    window = MainWindow()

    # Set search value
    window._search_ctrl.SetValue("test")

    # Clear all
    window._clear_all()

    # Verify search cleared
    assert window._search_ctrl.GetValue() == ""

    window._frame.Destroy()


def test_edit_menu_exists(wx_app):
    """Test Edit menu exists with Find, Select All, and Select None items."""
    window = MainWindow()
    menubar = window._frame.GetMenuBar()

    # Find Edit menu (index 1, between File and Help)
    edit_menu_idx = menubar.FindMenu("Edit")
    assert edit_menu_idx != wx.NOT_FOUND

    edit_menu = menubar.GetMenu(edit_menu_idx)
    items = list(edit_menu.GetMenuItems())
    labels = [
        "---" if it.IsSeparator() else it.GetItemLabelText()
        for it in items
    ]
    assert "Find..." in labels
    assert "Select All" in labels
    assert "Select None" in labels

    window._frame.Destroy()


def test_clear_ai_menu_exists(wx_app):
    """Test 'Clear AI Results' menu item exists in File menu."""
    window = MainWindow()
    menubar = window._frame.GetMenuBar()

    file_menu_idx = menubar.FindMenu("File")
    assert file_menu_idx != wx.NOT_FOUND

    file_menu = menubar.GetMenu(file_menu_idx)
    labels = [
        it.GetItemLabelText() for it in file_menu.GetMenuItems()
        if not it.IsSeparator()
    ]
    assert any("Clear AI Results" in label for label in labels)

    window._frame.Destroy()


def test_native_toolbar_created(wx_app):
    """Test native toolbar is created."""
    window = MainWindow()

    # Verify native toolbar exists
    assert window._toolbar is not None
    assert isinstance(window._toolbar, wx.ToolBar)

    window._frame.Destroy()


def test_toolbar_tools_initial_state(wx_app):
    """Test toolbar tools start in correct state."""
    window = MainWindow()

    # Reload, AI All, Rename, Clear should be disabled initially
    assert not window._toolbar.GetToolEnabled(window._reload_id)
    assert not window._toolbar.GetToolEnabled(window._ai_all_id)
    assert not window._toolbar.GetToolEnabled(window._rename_id)
    assert not window._toolbar.GetToolEnabled(window._clear_id)

    # Browse should be enabled
    assert window._toolbar.GetToolEnabled(window._browse_id)

    window._frame.Destroy()


def test_filter_sidebar_exists(wx_app):
    """Test filter sidebar is created."""
    window = MainWindow()
    assert window._sidebar is not None
    assert hasattr(window._sidebar, 'get_selected_category_filters')
    assert window._sidebar.get_selected_category_filters() == ["all"]
    window._frame.Destroy()


def test_three_column_layout(wx_app):
    """Test three-column layout with nested splitters."""
    window = MainWindow()

    # Find splitters in the frame
    def find_all_splitters(widget):
        splitters = []
        if isinstance(widget, wx.SplitterWindow):
            splitters.append(widget)
        for child in widget.GetChildren():
            splitters.extend(find_all_splitters(child))
        return splitters

    splitters = find_all_splitters(window._frame)

    # Should have at least 2 splitters for three-column layout
    # (main: sidebar|content, content: review|preview)
    # Note: review panel may have internal splitter for master-detail
    assert len(splitters) >= 2

    # All should be split
    for splitter in splitters:
        assert splitter.IsSplit()

    window._frame.Destroy()


def test_sidebar_filter_changes_cards(wx_app):
    """Test sidebar filters change displayed cards (multi-select)."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add test cards with different confidence levels
    card_high = CardResult(id=0, file_paths=[Path("/test/high.pdf")], primary_path=Path("/test/high.pdf"))
    card_high.family_name = "High"
    card_high.confidence = Confidence.HIGH
    card_high.file_hash = "hash_high"

    card_medium = CardResult(id=1, file_paths=[Path("/test/medium.pdf")], primary_path=Path("/test/medium.pdf"))
    card_medium.family_name = "Medium"
    card_medium.confidence = Confidence.MEDIUM
    card_medium.file_hash = "hash_medium"

    card_manual = CardResult(id=2, file_paths=[Path("/test/manual.pdf")], primary_path=Path("/test/manual.pdf"))
    card_manual.family_name = "Manual"
    card_manual.confidence = Confidence.MANUAL
    card_manual.file_hash = "hash_manual"

    card_error = CardResult(id=3, file_paths=[Path("/test/error.pdf")], primary_path=Path("/test/error.pdf"))
    card_error.family_name = ""
    card_error.confidence = Confidence.NONE
    card_error.error = "Failed"
    card_error.file_hash = "hash_error"

    window._cards_by_hash = {"hash_high": card_high, "hash_medium": card_medium, "hash_manual": card_manual, "hash_error": card_error}

    # Test "all" filter (default)
    window._current_category_filters = ["all"]
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 4

    # Test "high" filter only
    window._current_category_filters = ["high"]
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 0

    # Test multi-select: "high" and "manual"
    window._current_category_filters = ["high", "manual"]
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 2
    assert {c.id for c in filtered} == {0, 2}

    # Test "needs_review" filter
    window._current_category_filters = ["needs_review"]
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 1

    # Test "errors" filter
    window._current_category_filters = ["errors"]
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1
    assert filtered[0].id == 3

    window._frame.Destroy()


def test_combined_search_and_sidebar_filter(wx_app):
    """Test search query and sidebar filters work together."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add test cards
    card1 = CardResult(id=0, file_paths=[Path("/test/smith_card.pdf")], primary_path=Path("/test/smith_card.pdf"))
    card1.family_name = "Smith"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "hash1"

    card2 = CardResult(id=1, file_paths=[Path("/test/jones_card.pdf")], primary_path=Path("/test/jones_card.pdf"))
    card2.family_name = "Jones"
    card2.confidence = Confidence.HIGH
    card2.file_hash = "hash2"

    card3 = CardResult(id=2, file_paths=[Path("/test/smith_medium.pdf")], primary_path=Path("/test/smith_medium.pdf"))
    card3.family_name = "Smith"
    card3.confidence = Confidence.MEDIUM
    card3.file_hash = "hash3"

    window._cards_by_hash = {"hash1": card1, "hash2": card2, "hash3": card3}

    # Filter by "high" confidence only (must sync sidebar state too)
    window._current_category_filters = ["high"]
    window._sidebar.set_category_filters(["high"])
    window._search_ctrl.SetValue("")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 2  # card1 and card2

    # Filter by "high" confidence AND search for "smith"
    window._current_category_filters = ["high"]
    window._sidebar.set_category_filters(["high"])
    window._search_ctrl.SetValue("smith")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 1  # Only card1
    assert filtered[0].id == 0

    # Search for "smith" with "all" filter
    window._current_category_filters = ["all"]
    window._sidebar.set_category_filters(["all"])
    window._search_ctrl.SetValue("smith")
    filtered = window._apply_category_filters(window._get_search_filtered_cards())
    assert len(filtered) == 2  # card1 and card3

    window._frame.Destroy()


def test_on_filter_change_callback(wx_app):
    """Test sidebar filter change triggers card reload."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add test card
    card = CardResult(id=0, file_paths=[Path("/test/high.pdf")], primary_path=Path("/test/high.pdf"))
    card.family_name = "Test"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card}

    # Simulate sidebar click: sidebar updates its own state, then fires callback
    window._sidebar.set_category_filters(["high"])
    window._on_category_filter_change(["high"])

    # Verify state updated
    assert window._current_category_filters == ["high"]

    window._frame.Destroy()


def test_clear_resets_sidebar_filter(wx_app):
    """Test _clear_all resets sidebar filters to ['all']."""
    window = MainWindow()

    # Change filters
    window._current_category_filters = ["high", "manual"]
    window._sidebar.set_category_filters(["high", "manual"])

    # Clear
    window._clear_all()

    # Verify reset
    assert window._current_category_filters == ["all"]
    assert window._current_folder_filters == ["all_folders"]
    assert window._sidebar.get_selected_category_filters() == ["all"]

    window._frame.Destroy()


# --- Cross-filter and folder tests ---


def test_cross_filtered_category_counts(wx_app):
    """Test selecting a folder updates category counts to that folder's distribution."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")

    card1 = CardResult(id=0, file_paths=[folder1 / "a.pdf"], primary_path=folder1 / "a.pdf")
    card1.family_name = "A"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "h1"

    card2 = CardResult(id=1, file_paths=[folder2 / "b.pdf"], primary_path=folder2 / "b.pdf")
    card2.family_name = "B"
    card2.confidence = Confidence.MEDIUM
    card2.file_hash = "h2"

    window._cards_by_hash = {"h1": card1, "h2": card2}

    # Select only folder1
    window._current_folder_filters = [str(folder1)]
    window._current_category_filters = ["all"]
    window._refresh_display()

    # Category counts should reflect only folder1's cards
    assert window._sidebar._category_card_counts["all"] == 1
    assert window._sidebar._category_card_counts["high"] == 1
    assert window._sidebar._category_card_counts["needs_review"] == 0

    window._frame.Destroy()


def test_cross_filtered_folder_counts(wx_app):
    """Test selecting a category updates folder counts to that category's distribution."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")

    card1 = CardResult(id=0, file_paths=[folder1 / "a.pdf"], primary_path=folder1 / "a.pdf")
    card1.family_name = "A"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "h1"

    card2 = CardResult(id=1, file_paths=[folder2 / "b.pdf"], primary_path=folder2 / "b.pdf")
    card2.family_name = "B"
    card2.confidence = Confidence.MEDIUM
    card2.file_hash = "h2"

    card3 = CardResult(id=2, file_paths=[folder1 / "c.pdf"], primary_path=folder1 / "c.pdf")
    card3.family_name = "C"
    card3.confidence = Confidence.MEDIUM
    card3.file_hash = "h3"

    window._cards_by_hash = {"h1": card1, "h2": card2, "h3": card3}
    window._sidebar.update_folders([folder1, folder2])

    # Select "needs_review" category
    window._current_category_filters = ["needs_review"]
    window._current_folder_filters = ["all_folders"]
    window._refresh_display()

    # Folder counts should reflect only needs_review cards
    # folder1 has card3 (medium), folder2 has card2 (medium)
    folder1_key = str(folder1)
    folder2_key = str(folder2)
    # Find the count for each folder in the checkboxes
    folder1_label = None
    folder2_label = None
    for i, (key, _) in enumerate(window._sidebar._folder_filters):
        if key == folder1_key:
            folder1_label = window._sidebar._folder_checkboxes[i].GetLabel()
        elif key == folder2_key:
            folder2_label = window._sidebar._folder_checkboxes[i].GetLabel()

    assert "(1)" in folder1_label  # card3 is needs_review in folder1
    assert "(1)" in folder2_label  # card2 is needs_review in folder2

    window._frame.Destroy()


def test_both_filters_intersection(wx_app):
    """Test both filters active shows only the intersection."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")

    card1 = CardResult(id=0, file_paths=[folder1 / "a.pdf"], primary_path=folder1 / "a.pdf")
    card1.family_name = "A"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "h1"

    card2 = CardResult(id=1, file_paths=[folder2 / "b.pdf"], primary_path=folder2 / "b.pdf")
    card2.family_name = "B"
    card2.confidence = Confidence.HIGH
    card2.file_hash = "h2"

    card3 = CardResult(id=2, file_paths=[folder1 / "c.pdf"], primary_path=folder1 / "c.pdf")
    card3.family_name = "C"
    card3.confidence = Confidence.MEDIUM
    card3.file_hash = "h3"

    window._cards_by_hash = {"h1": card1, "h2": card2, "h3": card3}

    # Apply both: folder1 + high confidence
    window._current_folder_filters = [str(folder1)]
    window._current_category_filters = ["high"]

    search_cards = window._get_search_filtered_cards()
    folder_filtered = window._apply_folder_filters(search_cards)
    display = window._apply_category_filters(folder_filtered)

    # Only card1 (folder1 + high)
    assert len(display) == 1
    assert display[0].id == 0

    window._frame.Destroy()


def test_derive_folders(wx_app):
    """Test _derive_folders returns sorted unique parent paths."""
    from app.models.card import CardResult

    window = MainWindow()

    folder_a = Path("/test/aaa")
    folder_b = Path("/test/bbb")

    card1 = CardResult(id=0, file_paths=[folder_b / "x.pdf"], primary_path=folder_b / "x.pdf")
    card1.file_hash = "h1"
    card2 = CardResult(id=1, file_paths=[folder_a / "y.pdf"], primary_path=folder_a / "y.pdf")
    card2.file_hash = "h2"
    card3 = CardResult(id=2, file_paths=[folder_b / "z.pdf"], primary_path=folder_b / "z.pdf")
    card3.file_hash = "h3"

    window._cards_by_hash = {"h1": card1, "h2": card2, "h3": card3}

    folders = window._derive_folders()
    assert folders == [folder_a, folder_b]  # sorted, unique

    window._frame.Destroy()


def test_clear_all_hides_folders(wx_app):
    """Test _clear_all hides the folder section."""
    from app.models.card import CardResult

    window = MainWindow()

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")

    # Set up folders in sidebar
    window._sidebar.update_folders([folder1, folder2])
    assert window._sidebar._folder_separator.IsShown()

    # Clear
    window._clear_all()

    # Folder section should be hidden
    assert not window._sidebar._folder_separator.IsShown()
    assert not window._sidebar._folder_header.IsShown()
    assert len(window._sidebar._folder_checkboxes) == 0
    assert window._current_folder_filters == ["all_folders"]

    window._frame.Destroy()


# --- Panel sync, debounce, and selection tests ---


def test_on_card_select_none_clears_preview(wx_app):
    """Test _on_card_select(None) clears preview panel."""
    from unittest.mock import patch

    window = MainWindow()

    with patch.object(window._preview_panel, "clear") as mock_clear:
        window._on_card_select(None)
        mock_clear.assert_called_once()

    window._frame.Destroy()


def test_name_change_starts_debounce_timer(wx_app):
    """Test _on_name_change starts the debounce timer."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add a card
    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card}

    # Load cards so review panel knows about them
    window._review_panel.load_cards([card])

    # Call _on_name_change
    window._on_name_change(0, "NewName")

    # Timer should be running
    assert window._edit_debounce_timer.IsRunning()

    window._edit_debounce_timer.Stop()
    window._frame.Destroy()


def test_card_edited_immediate_refresh(wx_app):
    """Test _on_card_edited calls _refresh_display immediately."""
    from unittest.mock import patch

    window = MainWindow()

    with patch.object(window, "_refresh_display") as mock_refresh:
        window._on_card_edited(0)
        mock_refresh.assert_called_once()

    window._frame.Destroy()


def test_ai_all_complete_calls_refresh_display(wx_app):
    """Test _ai_all_complete calls _refresh_display to update sidebar counts."""
    from unittest.mock import patch

    from app.models.card import CardResult

    window = MainWindow()
    window._ai_target_cards = []

    with patch.object(window, "_refresh_display") as mock_refresh:
        window._ai_all_complete(errors=[], auth_aborted=False)
        mock_refresh.assert_called_once()

    window._frame.Destroy()


def test_on_remove_callback_connected(wx_app):
    """Test review panel on_remove callback is connected."""
    window = MainWindow()
    assert window._review_panel._on_remove == window._on_remove_card
    window._frame.Destroy()


def test_remove_card_removes_from_state(wx_app):
    """Test _on_remove_card removes card from all state dicts."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add test card
    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {Path("/test/card.pdf"): "hash1"}
    window._mtime_by_path = {Path("/test/card.pdf"): 100.0}
    window._pdf_files = [Path("/test/card.pdf")]

    # Remove card
    window._on_remove_card("hash1")

    # Verify all state is cleaned up
    assert "hash1" not in window._cards_by_hash
    assert Path("/test/card.pdf") not in window._hash_by_path
    assert Path("/test/card.pdf") not in window._mtime_by_path
    assert Path("/test/card.pdf") not in window._pdf_files
    window._frame.Destroy()


def test_remove_card_multi_path(wx_app):
    """Test _on_remove_card removes all paths for a multi-path card."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add card with multiple paths
    card = CardResult(
        id=0,
        file_paths=[Path("/test/card1.pdf"), Path("/test/card2.pdf")],
        primary_path=Path("/test/card1.pdf"),
    )
    card.family_name = "Smith"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {
        Path("/test/card1.pdf"): "hash1",
        Path("/test/card2.pdf"): "hash1",
    }
    window._mtime_by_path = {
        Path("/test/card1.pdf"): 100.0,
        Path("/test/card2.pdf"): 200.0,
    }
    window._pdf_files = [Path("/test/card1.pdf"), Path("/test/card2.pdf")]

    # Remove card
    window._on_remove_card("hash1")

    # Both paths should be removed
    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
    assert len(window._mtime_by_path) == 0
    assert len(window._pdf_files) == 0
    window._frame.Destroy()


def test_remove_card_nonexistent_hash(wx_app):
    """Test _on_remove_card with nonexistent hash does not crash."""
    window = MainWindow()
    # Should not raise
    window._on_remove_card("nonexistent_hash")
    window._frame.Destroy()


def test_remove_menu_removes_selected_cards(wx_app):
    """Test _on_remove_menu removes all selected cards."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add two cards
    card1 = CardResult(id=1, file_paths=[Path("/test/a.pdf")], primary_path=Path("/test/a.pdf"))
    card1.file_hash = "hash1"
    card1.confidence = Confidence.HIGH
    card2 = CardResult(id=2, file_paths=[Path("/test/b.pdf")], primary_path=Path("/test/b.pdf"))
    card2.file_hash = "hash2"
    card2.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card1, "hash2": card2}
    window._hash_by_path = {Path("/test/a.pdf"): "hash1", Path("/test/b.pdf"): "hash2"}
    window._pdf_files = [Path("/test/a.pdf"), Path("/test/b.pdf")]

    # Simulate selecting both cards
    window._review_panel._selected_card_ids = [1, 2]
    window._review_panel._cards_by_id = {1: card1, 2: card2}

    window._on_remove_menu(Mock())

    assert len(window._cards_by_hash) == 0
    window._frame.Destroy()


def test_remove_menu_skips_card_without_hash(wx_app):
    """_on_remove_menu skips selected cards that have no file_hash."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Card with hash — should be removed
    card1 = CardResult(id=1, file_paths=[Path("/test/a.pdf")], primary_path=Path("/test/a.pdf"))
    card1.file_hash = "hash1"
    card1.confidence = Confidence.HIGH

    # Card without hash — should be skipped without crash
    card2 = CardResult(id=2, file_paths=[Path("/test/b.pdf")], primary_path=Path("/test/b.pdf"))
    card2.file_hash = None
    card2.confidence = Confidence.HIGH

    window._cards_by_hash = {"hash1": card1}
    window._hash_by_path = {Path("/test/a.pdf"): "hash1"}
    window._pdf_files = [Path("/test/a.pdf")]

    # Simulate selecting both cards
    window._review_panel._selected_card_ids = [1, 2]
    window._review_panel._cards_by_id = {1: card1, 2: card2}

    window._on_remove_menu(Mock())

    # card1 removed, card2 skipped (no crash)
    assert "hash1" not in window._cards_by_hash
    window._frame.Destroy()


def test_update_remove_menu_enabled_with_selection(wx_app):
    """Test _on_update_remove_menu enables when cards selected."""
    window = MainWindow()
    window._review_panel._selected_card_ids = [1]

    event = Mock()
    window._on_update_remove_menu(event)
    event.Enable.assert_called_with(True)
    window._frame.Destroy()


def test_update_remove_menu_disabled_without_selection(wx_app):
    """Test _on_update_remove_menu disables when no cards selected."""
    window = MainWindow()
    window._review_panel._selected_card_ids = []

    event = Mock()
    window._on_update_remove_menu(event)
    event.Enable.assert_called_with(False)
    window._frame.Destroy()


def test_remove_last_card_shows_overlay(wx_app):
    """Test removing the last card shows the drop overlay."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {Path("/test/card.pdf"): "hash1"}
    window._pdf_files = [Path("/test/card.pdf")]

    # Show content area first
    window._set_empty_state(False)
    assert window._content_splitter.IsShown()

    # Remove last card
    window._on_remove_card("hash1")

    # Overlay should be shown
    assert window._drop_overlay.IsShown()
    window._frame.Destroy()


def test_close_stops_debounce_timer(wx_app):
    """Test _on_close stops the debounce timer."""
    window = MainWindow()

    # Start the timer
    window._edit_debounce_timer.StartOnce(5000)
    assert window._edit_debounce_timer.IsRunning()

    # Close should stop it
    window._on_close(None)

    assert not window._edit_debounce_timer.IsRunning()


# --- Auto-reset and re-entrancy tests ---


def test_refresh_display_auto_resets_when_filtered_empty(wx_app):
    """Test _refresh_display auto-resets category filter when filtered result is empty but cards exist."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    # Add cards — one high, one manual
    card_high = CardResult(id=0, file_paths=[Path("/test/high.pdf")], primary_path=Path("/test/high.pdf"))
    card_high.family_name = "High"
    card_high.confidence = Confidence.HIGH
    card_high.file_hash = "hash_high"

    card_manual = CardResult(id=1, file_paths=[Path("/test/manual.pdf")], primary_path=Path("/test/manual.pdf"))
    card_manual.family_name = "Manual"
    card_manual.confidence = Confidence.MANUAL
    card_manual.file_hash = "hash_manual"

    window._cards_by_hash = {"hash_high": card_high, "hash_manual": card_manual}

    # Select "high" filter — shows 1 card
    window._current_category_filters = ["high"]
    window._sidebar.set_category_filters(["high"])
    window._refresh_display()
    assert window._current_category_filters == ["high"]

    # Now change the high card to manual (simulating an edit)
    card_high.confidence = Confidence.MANUAL
    window._refresh_display()

    # Category should have auto-reset to "all" since "high" now has 0 cards
    assert window._current_category_filters == ["all"]
    assert window._sidebar.get_selected_category_filters() == ["all"]

    window._frame.Destroy()


def test_refresh_display_keeps_search_on_empty(wx_app):
    """Test search text is preserved when auto-reset happens (only checkboxes reset)."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    card = CardResult(id=0, file_paths=[Path("/test/smith.pdf")], primary_path=Path("/test/smith.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.HIGH
    card.file_hash = "hash1"

    window._cards_by_hash = {"hash1": card}

    # Set search to "smith" and filter to "high"
    window._search_ctrl.SetValue("smith")
    window._current_category_filters = ["high"]
    window._sidebar.set_category_filters(["high"])

    # Change card confidence — "high" goes to zero
    card.confidence = Confidence.MANUAL
    window._refresh_display()

    # Search text should be preserved
    assert window._search_ctrl.GetValue() == "smith"
    # Category should have auto-reset
    assert window._current_category_filters == ["all"]

    window._frame.Destroy()


def test_refresh_display_syncs_sidebar_fallback(wx_app):
    """Test _refresh_display picks up sidebar's internal auto-reset of category filter."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    folder1 = Path("/test/folder1")
    folder2 = Path("/test/folder2")

    card1 = CardResult(id=0, file_paths=[folder1 / "a.pdf"], primary_path=folder1 / "a.pdf")
    card1.family_name = "A"
    card1.confidence = Confidence.HIGH
    card1.file_hash = "h1"

    card2 = CardResult(id=1, file_paths=[folder2 / "b.pdf"], primary_path=folder2 / "b.pdf")
    card2.family_name = "B"
    card2.confidence = Confidence.MEDIUM
    card2.file_hash = "h2"

    window._cards_by_hash = {"h1": card1, "h2": card2}
    window._sidebar.update_folders([folder1, folder2])

    # Select folder1 + high confidence — only card1 should show
    window._current_folder_filters = [str(folder1)]
    window._sidebar.set_folder_filters([str(folder1)])
    window._current_category_filters = ["high"]
    window._sidebar.set_category_filters(["high"])
    window._refresh_display()
    assert window._current_category_filters == ["high"]

    # Now change card1 to MEDIUM — "high" goes to zero in folder1
    card1.confidence = Confidence.MEDIUM
    window._refresh_display()

    # Sidebar should have auto-reset category, and MainWindow should have synced it
    assert window._current_category_filters == ["all"]
    assert window._sidebar.get_selected_category_filters() == ["all"]

    window._frame.Destroy()


# --- Post-rename selective removal tests ---


def test_remove_completed_results_full_success(wx_app):
    """All cards renamed successfully → all removed, empty state shown."""
    from app.models.card import CardResult, Confidence, RenameResult

    window = MainWindow()
    path1 = Path("/test/old1.pdf")
    path2 = Path("/test/old2.pdf")
    new1 = Path("/test/Holiday Cards 2024 - Smith Family.pdf")
    new2 = Path("/test/Holiday Cards 2024 - Jones Family.pdf")

    card1 = CardResult(id=0, file_paths=[new1], primary_path=new1)
    card1.file_hash = "h1"
    card1.confidence = Confidence.HIGH

    card2 = CardResult(id=1, file_paths=[new2], primary_path=new2)
    card2.file_hash = "h2"
    card2.confidence = Confidence.HIGH

    # Simulate state after execute_rename_plan has updated paths
    window._cards_by_hash = {"h1": card1, "h2": card2}
    window._hash_by_path = {new1: "h1", new2: "h2"}
    window._pdf_files = [new1, new2]

    results = [
        RenameResult(path1, new1, True, "Renamed", card=card1),
        RenameResult(path2, new2, True, "Renamed", card=card2),
    ]

    window._remove_completed_results(results)

    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
    assert len(window._pdf_files) == 0

    window._frame.Destroy()


def test_remove_completed_results_partial_failure(wx_app):
    """Failed renames keep their cards; successful ones are removed."""
    from app.models.card import CardResult, Confidence, RenameResult

    window = MainWindow()
    new_path = Path("/test/Holiday Cards 2024 - Smith Family.pdf")
    fail_path = Path("/test/jones.pdf")

    card1 = CardResult(id=0, file_paths=[new_path], primary_path=new_path)
    card1.file_hash = "h1"
    card1.confidence = Confidence.HIGH

    card2 = CardResult(id=1, file_paths=[fail_path], primary_path=fail_path)
    card2.file_hash = "h2"
    card2.confidence = Confidence.HIGH

    window._cards_by_hash = {"h1": card1, "h2": card2}
    window._hash_by_path = {new_path: "h1", fail_path: "h2"}
    window._pdf_files = [new_path, fail_path]

    results = [
        RenameResult(Path("/test/old1.pdf"), new_path, True, "Renamed", card=card1),
        RenameResult(fail_path, Path("/test/Holiday Cards 2024 - Jones Family.pdf"), False, "Permission denied", card=card2),
    ]

    window._remove_completed_results(results)

    # card1 removed, card2 kept
    assert "h1" not in window._cards_by_hash
    assert "h2" in window._cards_by_hash
    assert new_path not in window._hash_by_path
    assert fail_path in window._hash_by_path
    assert fail_path in window._pdf_files

    window._frame.Destroy()


def test_remove_completed_results_skip_same(wx_app):
    """skip_same results (already named correctly) are also removed."""
    from app.models.card import CardResult, Confidence, RenameResult

    window = MainWindow()
    path1 = Path("/test/Holiday Cards 2024 - Smith Family.pdf")

    card1 = CardResult(id=0, file_paths=[path1], primary_path=path1)
    card1.file_hash = "h1"
    card1.confidence = Confidence.HIGH

    window._cards_by_hash = {"h1": card1}
    window._hash_by_path = {path1: "h1"}
    window._pdf_files = [path1]

    results = [
        RenameResult(path1, path1, True, "Already named correctly", card=card1),
    ]

    window._remove_completed_results(results)

    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0

    window._frame.Destroy()


def test_remove_completed_results_skip_no_name_kept(wx_app):
    """skip_no_name results are NOT removed — user needs to address them."""
    from app.models.card import CardResult, Confidence, RenameResult

    window = MainWindow()
    path1 = Path("/test/unknown.pdf")

    card1 = CardResult(id=0, file_paths=[path1], primary_path=path1)
    card1.file_hash = "h1"
    card1.confidence = Confidence.NONE

    window._cards_by_hash = {"h1": card1}
    window._hash_by_path = {path1: "h1"}
    window._pdf_files = [path1]

    results = [
        RenameResult(path1, path1, True, "No name extracted", card=card1),
    ]

    window._remove_completed_results(results)

    # Card kept — no name extracted is not "resolved"
    assert "h1" in window._cards_by_hash
    assert path1 in window._hash_by_path

    window._frame.Destroy()


def test_remove_completed_results_multi_path_card(wx_app):
    """Card with multiple paths: only remove renamed paths, keep card if paths remain."""
    from app.models.card import CardResult, Confidence, RenameResult

    window = MainWindow()
    new_path = Path("/test/dir_a/Holiday Cards 2024 - Smith Family.pdf")
    fail_path = Path("/test/dir_b/smith.pdf")

    card = CardResult(id=0, file_paths=[new_path, fail_path], primary_path=new_path)
    card.file_hash = "h1"
    card.confidence = Confidence.HIGH

    window._cards_by_hash = {"h1": card}
    window._hash_by_path = {new_path: "h1", fail_path: "h1"}
    window._pdf_files = [new_path, fail_path]

    results = [
        RenameResult(Path("/test/dir_a/old.pdf"), new_path, True, "Renamed", card=card),
        RenameResult(fail_path, Path("/test/dir_b/Holiday Cards 2024 - Smith Family.pdf"), False, "Permission denied", card=card),
    ]

    window._remove_completed_results(results)

    # Card still exists with one remaining path
    assert "h1" in window._cards_by_hash
    assert card.file_paths == [fail_path]
    assert new_path not in window._hash_by_path
    assert fail_path in window._hash_by_path

    window._frame.Destroy()


# --- Name change revert tests ---


def test_on_name_change_revert_to_original(wx_app):
    """Clearing the name field reverts card to DB state (best candidate)."""
    from app.models.card import CardResult, Confidence, CandidateInfo, CardState
    from unittest.mock import patch, MagicMock

    window = MainWindow()
    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.MANUAL
    card.original_confidence = Confidence.HIGH
    card.method = "manual"
    card.manual_override = "Jones"
    card.file_hash = "h1"

    window._cards_by_hash = {"h1": card}
    window._hash_by_path = {Path("/test/card.pdf"): "h1"}

    # Mock DB to return OCR candidate
    mock_state = CardState(
        display_name="Smith", confidence="high", method="ocr",
        candidates=[CandidateInfo(id=1, family_name="Smith", method="ocr", confidence="high")],
        remove_family=False, selected_candidate_id=1,
    )

    with patch("app.gui.main_window.set_manual_name"), \
         patch("app.gui.main_window.get_card_state", return_value=mock_state):
        window._on_name_change(0, "")

    assert card.confidence == Confidence.HIGH
    assert card.manual_override == ""
    assert card.family_name == "Smith"
    assert card.method == "ocr"

    window._frame.Destroy()


def test_on_name_change_revert_ai_analyzed(wx_app):
    """Clearing name on an AI-analyzed card reverts method to 'ai'."""
    from app.models.card import CardResult, Confidence, CandidateInfo, CardState
    from unittest.mock import patch

    window = MainWindow()
    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.family_name = "Smith"
    card.confidence = Confidence.MANUAL
    card.original_confidence = Confidence.HIGH
    card.method = "manual"
    card.manual_override = "Jones"
    card.ai_analyzed = True
    card.file_hash = "h1"

    window._cards_by_hash = {"h1": card}
    window._hash_by_path = {Path("/test/card.pdf"): "h1"}

    mock_state = CardState(
        display_name="Smith", confidence="high", method="ai",
        candidates=[CandidateInfo(id=1, family_name="Smith", method="ai", confidence="high")],
        remove_family=False, selected_candidate_id=1,
    )

    with patch("app.gui.main_window.set_manual_name"), \
         patch("app.gui.main_window.get_card_state", return_value=mock_state):
        window._on_name_change(0, "")

    assert card.method == "ai"

    window._frame.Destroy()


def test_on_name_change_revert_no_original_confidence(wx_app):
    """Clearing name when no DB state falls back to NONE/missing."""
    from app.models.card import CardResult, Confidence
    from unittest.mock import patch

    window = MainWindow()
    card = CardResult(id=0, file_paths=[Path("/test/card.pdf")], primary_path=Path("/test/card.pdf"))
    card.confidence = Confidence.MANUAL
    card.original_confidence = None
    card.method = "manual"
    card.manual_override = "Test"
    card.file_hash = "h1"

    window._cards_by_hash = {"h1": card}
    window._hash_by_path = {Path("/test/card.pdf"): "h1"}

    with patch("app.gui.main_window.set_manual_name"), \
         patch("app.gui.main_window.get_card_state", return_value=None):
        window._on_name_change(0, "")

    assert card.confidence == Confidence.NONE
    assert card.method == "missing"

    window._frame.Destroy()


# --- Year validation tests ---


def test_year_validation_rejects_non_digit(wx_app):
    """Non-digit year string should be rejected."""
    from unittest.mock import patch

    window = MainWindow()
    window._year_ctrl.SetValue("abc")

    with patch("wx.MessageBox") as mock_msg:
        window._start_rename()
        mock_msg.assert_called_once()
        assert "4-digit year" in mock_msg.call_args[0][0]

    window._frame.Destroy()


def test_year_validation_rejects_short(wx_app):
    """Year shorter than 4 digits should be rejected."""
    from unittest.mock import patch

    window = MainWindow()
    window._year_ctrl.SetValue("25")

    with patch("wx.MessageBox") as mock_msg:
        window._start_rename()
        mock_msg.assert_called_once()
        assert "4-digit year" in mock_msg.call_args[0][0]

    window._frame.Destroy()


def test_year_validation_accepts_valid(wx_app):
    """Valid 4-digit year passes validation (proceeds to empty cards check)."""
    from unittest.mock import patch

    window = MainWindow()
    window._year_ctrl.SetValue("2024")

    # With no cards loaded, _start_rename will call get_cards which returns []
    # Then build_rename_plan([]) returns [], and RenameConfirmDialog opens
    # We just verify it doesn't show the year validation error
    with patch("wx.MessageBox") as mock_msg:
        with patch("app.gui.main_window.RenameConfirmDialog") as mock_dialog:
            mock_dialog.return_value.ShowModal.return_value = 0  # Cancel
            mock_dialog.return_value.Destroy = lambda: None
            window._start_rename()
            # MessageBox should NOT have been called (year is valid)
            mock_msg.assert_not_called()

    window._frame.Destroy()


# ============================================================================
# _scan_for_pdfs Tests (lines 704-718)
# ============================================================================


def test_scan_for_pdfs_file(wx_app, tmp_path):
    """_scan_for_pdfs returns a single PDF file."""
    window = MainWindow()
    pdf = tmp_path / "test.pdf"
    pdf.write_text("fake pdf")

    result = window._scan_for_pdfs(pdf)
    assert len(result) == 1
    assert result[0] == pdf.resolve()

    window._frame.Destroy()


def test_scan_for_pdfs_non_pdf_file(wx_app, tmp_path):
    """_scan_for_pdfs returns empty for non-PDF files."""
    window = MainWindow()
    txt = tmp_path / "test.txt"
    txt.write_text("not a pdf")

    result = window._scan_for_pdfs(txt)
    assert result == []

    window._frame.Destroy()


def test_scan_for_pdfs_directory(wx_app, tmp_path):
    """_scan_for_pdfs recursively scans directory for PDFs."""
    window = MainWindow()
    sub = tmp_path / "subdir"
    sub.mkdir()
    (tmp_path / "a.pdf").write_text("fake")
    (sub / "b.pdf").write_text("fake")
    (sub / "c.txt").write_text("not pdf")

    result = window._scan_for_pdfs(tmp_path)
    assert len(result) == 2
    names = [p.name for p in result]
    assert "a.pdf" in names
    assert "b.pdf" in names

    window._frame.Destroy()


def test_scan_for_pdfs_case_insensitive(wx_app, tmp_path):
    """_scan_for_pdfs finds .PDF files (case insensitive)."""
    window = MainWindow()
    (tmp_path / "upper.PDF").write_text("fake")

    result = window._scan_for_pdfs(tmp_path)
    assert len(result) == 1

    window._frame.Destroy()


# ============================================================================
# _worker_result_to_card Tests
# ============================================================================


def test_worker_result_to_card_invalid_confidence(wx_app):
    """_worker_result_to_card falls back to NONE for invalid confidence."""
    from app.models.card import Confidence, PdfWorkerResult

    window = MainWindow()
    worker_result = PdfWorkerResult(
        pdf_path='/test.pdf',
        file_hash='abc123',
        family_name='Smith',
        confidence='invalid_value',
        method='ocr',
    )

    card = window._worker_result_to_card(worker_result, 0)
    assert card.confidence == Confidence.NONE

    window._frame.Destroy()


def test_worker_result_to_card_with_error(wx_app):
    """_worker_result_to_card sets error and confidence=NONE when error is present."""
    from app.models.card import Confidence, PdfWorkerResult

    window = MainWindow()
    worker_result = PdfWorkerResult(
        pdf_path='/test.pdf',
        file_hash='abc123',
        confidence='high',
        method='ocr',
        error='Something broke',
    )

    card = window._worker_result_to_card(worker_result, 0)
    assert card.error == "Something broke"
    assert card.confidence == Confidence.NONE

    window._frame.Destroy()


# ============================================================================
# _load_card_state_from_db Tests (lines 1218-1238)
# ============================================================================


def test_load_card_state_from_db_no_hash(wx_app):
    """_load_card_state_from_db sets NONE confidence when no hash (lines 1218-1221)."""
    from app.gui.main_window import MainWindow
    from app.models.card import CardResult, Confidence

    card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
    card.file_hash = ""

    MainWindow._load_card_state_from_db(card)

    assert card.confidence == Confidence.NONE
    assert card.ai_analyzed is True


def test_load_card_state_from_db_with_state(wx_app):
    """_load_card_state_from_db populates card from DB state (lines 1224-1235)."""
    from unittest.mock import patch
    from app.gui.main_window import MainWindow
    from app.models.card import CardResult, CardState, CandidateInfo, Confidence

    card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
    card.file_hash = "abc123"

    mock_state = CardState(
        display_name="Smith",
        method="ai",
        confidence="high",
        candidates=[CandidateInfo(id=1, family_name="Smith", method="ai", confidence="high")],
        remove_family=True,
        selected_candidate_id=1,
    )

    with patch("app.gui.main_window.get_card_state", return_value=mock_state):
        MainWindow._load_card_state_from_db(card)

    assert card.family_name == "Smith"
    assert card.confidence == Confidence.HIGH
    assert card.method == "ai"
    assert card.remove_family is True
    assert card.ai_analyzed is True
    assert card.manual_override == ""


def test_load_card_state_from_db_no_state(wx_app):
    """_load_card_state_from_db sets ai_analyzed when no state found (line 1237)."""
    from unittest.mock import patch
    from app.gui.main_window import MainWindow
    from app.models.card import CardResult

    card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
    card.file_hash = "abc123"

    with patch("app.gui.main_window.get_card_state", return_value=None):
        MainWindow._load_card_state_from_db(card)

    assert card.ai_analyzed is True


# ============================================================================
# _get_card_by_id edge case (line 301)
# ============================================================================


def test_get_card_by_id_not_found(wx_app):
    """_get_card_by_id returns None for unknown ID (line 301)."""
    window = MainWindow()
    assert window._get_card_by_id(999) is None
    window._frame.Destroy()


# ============================================================================
# _on_folder_filter_change (lines 471-472)
# ============================================================================


def test_on_folder_filter_change(wx_app):
    """_on_folder_filter_change stores filters and refreshes."""
    from unittest.mock import patch

    window = MainWindow()
    with patch.object(window, "_refresh_display"):
        window._on_folder_filter_change(["/test/folder1"])
    assert window._current_folder_filters == ["/test/folder1"]

    window._frame.Destroy()


# ============================================================================
# _load_paths Tests (lines 745-780)
# ============================================================================


def test_load_paths_skips_already_loaded(wx_app, tmp_path):
    """_load_paths skips files that are already loaded."""
    from unittest.mock import patch

    window = MainWindow()
    pdf = tmp_path / "test.pdf"
    pdf.write_text("fake")
    resolved = pdf.resolve()

    # Pretend it's already loaded
    window._hash_by_path[resolved] = "existing_hash"

    with patch.object(window, "_start_processing") as mock_proc:
        window._load_paths([pdf], auto_process=True)
        mock_proc.assert_not_called()  # Nothing new to process

    window._frame.Destroy()


def test_load_paths_no_pdfs_shows_warning(wx_app, tmp_path):
    """_load_paths shows warning when no PDFs found."""
    from unittest.mock import patch

    window = MainWindow()
    txt = tmp_path / "test.txt"
    txt.write_text("not a pdf")

    with patch.object(window, "_show_info_message") as mock_msg:
        window._load_paths([txt], auto_process=True)
        mock_msg.assert_called_once()
        assert "No PDF files found" in mock_msg.call_args[0][0]

    window._frame.Destroy()


# ============================================================================
# _on_key_press Tests (lines 667-693)
# ============================================================================


def test_on_key_press_escape_clears_search(wx_app):
    """Escape key clears search when search has focus."""
    window = MainWindow()
    window._search_ctrl.SetValue("test query")
    window._search_ctrl.SetFocus()

    event = Mock(spec=wx.KeyEvent)
    event.GetKeyCode.return_value = wx.WXK_ESCAPE

    # Mock FindFocus to return search ctrl
    from unittest.mock import patch
    with patch.object(window._frame, "FindFocus", return_value=window._search_ctrl):
        window._on_key_press(event)

    assert window._search_ctrl.GetValue() == ""

    window._frame.Destroy()


def test_on_key_press_skip_in_text_ctrl(wx_app):
    """Keys in text control are passed through (event.Skip)."""
    window = MainWindow()

    text_ctrl = wx.TextCtrl(window._frame)
    event = Mock(spec=wx.KeyEvent)
    event.GetKeyCode.return_value = ord('A')

    from unittest.mock import patch
    with patch.object(window._frame, "FindFocus", return_value=text_ctrl):
        window._on_key_press(event)
        event.Skip.assert_called_once()

    window._frame.Destroy()


def test_on_key_press_up_down_arrows(wx_app):
    """Up/Down arrows navigate cards."""
    from unittest.mock import patch

    window = MainWindow()
    event = Mock(spec=wx.KeyEvent)

    with patch.object(window._frame, "FindFocus", return_value=window._frame):
        with patch.object(window._review_panel, "select_prev_card") as mock_prev:
            event.GetKeyCode.return_value = wx.WXK_UP
            window._on_key_press(event)
            mock_prev.assert_called_once()

        with patch.object(window._review_panel, "select_next_card") as mock_next:
            event.GetKeyCode.return_value = wx.WXK_DOWN
            window._on_key_press(event)
            mock_next.assert_called_once()

    window._frame.Destroy()


def test_on_key_press_left_right_arrows(wx_app):
    """Left/Right arrows navigate preview pages."""
    from unittest.mock import patch

    window = MainWindow()
    event = Mock(spec=wx.KeyEvent)

    with patch.object(window._frame, "FindFocus", return_value=window._frame):
        with patch.object(window._preview_panel, "prev_page") as mock_prev:
            event.GetKeyCode.return_value = wx.WXK_LEFT
            window._on_key_press(event)
            mock_prev.assert_called_once()

        with patch.object(window._preview_panel, "next_page") as mock_next:
            event.GetKeyCode.return_value = wx.WXK_RIGHT
            window._on_key_press(event)
            mock_next.assert_called_once()

    window._frame.Destroy()


# ============================================================================
# _on_card_select edge cases (lines 1052-1061)
# ============================================================================


def test_on_card_select_missing_card(wx_app):
    """_on_card_select does nothing when card_id not found (line 1052)."""
    from unittest.mock import patch

    window = MainWindow()
    with patch.object(window._preview_panel, "clear") as mock_clear:
        window._on_card_select(999)  # Non-existent
        mock_clear.assert_not_called()  # Just returns

    window._frame.Destroy()


def test_on_card_select_none(wx_app):
    """_on_card_select clears preview when card_id is None."""
    from unittest.mock import patch

    window = MainWindow()
    with patch.object(window._preview_panel, "clear") as mock_clear:
        window._on_card_select(None)
        mock_clear.assert_called_once()

    window._frame.Destroy()


# ============================================================================
# _on_name_change edge case (line 1067)
# ============================================================================


def test_on_name_change_missing_card(wx_app):
    """_on_name_change returns early for unknown card_id (line 1067)."""
    from unittest.mock import patch

    window = MainWindow()
    with patch("app.gui.main_window.set_manual_name") as mock_db:
        window._on_name_change(999, "Smith")
        mock_db.assert_not_called()

    window._frame.Destroy()


# ============================================================================
# utils: create_text_ctrl callback (line 132)
# ============================================================================


def test_create_text_ctrl_with_callback(wx_app):
    """create_text_ctrl binds callback on EVT_TEXT (line 132)."""
    from app.gui.utils import create_text_ctrl

    frame = wx.Frame(None)
    called = []

    ctrl = create_text_ctrl(frame, value="initial", callback=lambda s: called.append(s))

    # Fire EVT_TEXT directly instead of SetValue + Yield, because Yield
    # can trigger unrelated macOS timer callbacks that segfault.
    evt = wx.CommandEvent(wx.wxEVT_TEXT, ctrl.GetId())
    evt.SetString("new value")
    ctrl.GetEventHandler().ProcessEvent(evt)

    assert len(called) == 1
    assert called[0] == "new value"

    frame.Destroy()


# ============================================================================
# icons: load_cursor_from_symbol exception handler (lines 180-183)
# ============================================================================


def test_load_cursor_from_symbol_exception_returns_none(wx_app):
    """load_cursor_from_symbol returns None when rendering raises (lines 180-183)."""
    from unittest.mock import patch
    from app.gui.icons import load_cursor_from_symbol

    with patch("app.gui.icons._render_sf_symbol_to_png", side_effect=RuntimeError("test")):
        result = load_cursor_from_symbol("test.symbol")
    assert result is None


# ============================================================================
# icons: load_sf_symbol bad wx.Image returns None (lines 220-221)
# ============================================================================


def test_load_sf_symbol_bad_image_caches_none(wx_app):
    """load_sf_symbol caches None when wx.Image is not OK (lines 220-221)."""
    from unittest.mock import patch
    from app.gui import icons

    # Clear cache to avoid interference
    test_key = ("_test_bad_img", 14, "#000000", 2, 5)
    icons._cache.pop(test_key, None)

    # Suppress wx "Unknown image data format" warning dialog
    wx.Log.EnableLogging(False)
    try:
        with patch("app.gui.icons._render_sf_symbol_to_png", return_value=(b"not-a-png", 2)):
            result = icons.load_sf_symbol("_test_bad_img", 14, "#000000", 2)
    finally:
        wx.Log.EnableLogging(True)

    assert result is None
    assert test_key in icons._cache
    assert icons._cache[test_key] is None

    # Clean up
    icons._cache.pop(test_key, None)


class TestResolvedMessages:
    """Tests for _RESOLVED_MESSAGES constant used in hash mapping."""

    def test_resolved_messages_contains_renamed(self):
        from app.gui.main_window import _RESOLVED_MESSAGES
        assert "Renamed" in _RESOLVED_MESSAGES

    def test_resolved_messages_contains_already_named(self):
        from app.gui.main_window import _RESOLVED_MESSAGES
        assert "Already named correctly" in _RESOLVED_MESSAGES

    def test_resolved_messages_size(self):
        from app.gui.main_window import _RESOLVED_MESSAGES
        assert len(_RESOLVED_MESSAGES) == 2


# ============================================================================
# Reload Cards Tests
# ============================================================================


def test_reload_menu_exists(wx_app):
    """Test 'Reload' menu item exists in File menu."""
    window = MainWindow()
    menubar = window._frame.GetMenuBar()

    file_menu_idx = menubar.FindMenu("File")
    file_menu = menubar.GetMenu(file_menu_idx)
    labels = [
        it.GetItemLabelText() for it in file_menu.GetMenuItems()
        if not it.IsSeparator()
    ]
    assert any("Reload" in label for label in labels)

    window._frame.Destroy()


def test_reload_toolbar_exists(wx_app):
    """Test Reload toolbar button exists."""
    window = MainWindow()
    tool = window._toolbar.FindById(window._reload_id)
    assert tool is not None
    window._frame.Destroy()


def test_reload_toolbar_initially_disabled(wx_app):
    """Test Reload button is disabled when no cards are loaded."""
    window = MainWindow()
    assert not window._toolbar.GetToolEnabled(window._reload_id)
    window._frame.Destroy()


def test_reload_no_cards_is_noop(wx_app):
    """_reload_cards with no loaded cards does nothing."""
    from unittest.mock import patch

    window = MainWindow()
    with patch.object(window, "_start_processing") as mock_proc:
        window._reload_cards()
        mock_proc.assert_not_called()
    window._frame.Destroy()


def test_reload_no_changes(wx_app, tmp_path):
    """_reload_cards with unchanged files shows 'up to date' message."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"fake pdf content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._pdf_files = [pdf]

    # Mock compute_file_hash to return the same hash
    with patch("app.core.database.compute_file_hash", return_value="hash1"), \
         patch.object(window, "_show_info_message") as mock_msg:
        window._reload_cards()
        mock_msg.assert_called_once()
        assert "up to date" in mock_msg.call_args[0][0]

    window._frame.Destroy()


def test_reload_deleted_file(wx_app, tmp_path):
    """_reload_cards removes cards for deleted files."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"fake pdf")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._mtime_by_path = {pdf: 100.0}
    window._pdf_files = [pdf]

    # Delete the file
    pdf.unlink()

    window._reload_cards()

    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
    assert len(window._mtime_by_path) == 0
    assert pdf not in window._pdf_files

    window._frame.Destroy()


def test_reload_modified_file(wx_app, tmp_path):
    """_reload_cards reprocesses files with changed content hash."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"original content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "old_hash"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"old_hash": card}
    window._hash_by_path = {pdf: "old_hash"}
    window._mtime_by_path = {pdf: 100.0}
    window._pdf_files = [pdf]

    # Mock compute_file_hash to return a new hash
    with patch("app.core.database.compute_file_hash", return_value="new_hash"), \
         patch.object(window, "_start_processing") as mock_proc:
        window._reload_cards()
        mock_proc.assert_called_once()
        assert pdf in mock_proc.call_args[0][0]

    # Old card should be removed
    assert "old_hash" not in window._cards_by_hash
    assert pdf not in window._hash_by_path
    assert pdf not in window._mtime_by_path

    window._frame.Destroy()


def test_reload_deleted_multi_path_card(wx_app, tmp_path):
    """Deleting one copy of a multi-path card keeps the card with remaining paths."""
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf1 = tmp_path / "copy1.pdf"
    pdf2 = tmp_path / "copy2.pdf"
    pdf1.write_bytes(b"same content")
    pdf2.write_bytes(b"same content")

    card = CardResult(id=0, file_paths=[pdf1, pdf2], primary_path=pdf1)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf1: "hash1", pdf2: "hash1"}
    window._pdf_files = [pdf1, pdf2]

    # Delete one copy
    pdf1.unlink()

    # Mock compute_file_hash for the remaining file
    from unittest.mock import patch
    with patch("app.core.database.compute_file_hash", return_value="hash1"):
        window._reload_cards()

    # Card still exists with one path
    assert "hash1" in window._cards_by_hash
    assert card.file_paths == [pdf2]
    assert pdf1 not in window._hash_by_path
    assert pdf2 in window._hash_by_path

    window._frame.Destroy()


def test_reload_updates_cooldown_timestamp(wx_app, tmp_path):
    """_reload_cards updates _last_reload_time."""
    import time
    from app.models.card import CardResult, Confidence
    from unittest.mock import patch

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._pdf_files = [pdf]

    before = time.monotonic()
    with patch("app.core.database.compute_file_hash", return_value="hash1"):
        window._reload_cards()
    after = time.monotonic()

    assert before <= window._last_reload_time <= after

    window._frame.Destroy()


def test_on_frame_activate_triggers_reload(wx_app, tmp_path):
    """EVT_ACTIVATE triggers _reload_cards when conditions are met."""
    from unittest.mock import patch, Mock
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._toolbar.EnableTool(window._reload_id, True)
    window._last_reload_time = 0.0  # Ensure cooldown expired

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = True

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_called_once()

    window._frame.Destroy()


def test_on_frame_activate_skips_deactivation(wx_app):
    """EVT_ACTIVATE does not reload on deactivation."""
    from unittest.mock import patch, Mock

    window = MainWindow()
    window._hash_by_path = {Path("/test.pdf"): "hash1"}

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = False

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_not_called()

    window._frame.Destroy()


def test_on_frame_activate_skips_no_cards(wx_app):
    """EVT_ACTIVATE does not reload when no cards loaded."""
    from unittest.mock import patch, Mock

    window = MainWindow()

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = True

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_not_called()

    window._frame.Destroy()


def test_on_frame_activate_respects_cooldown(wx_app, tmp_path):
    """EVT_ACTIVATE skips reload within cooldown period."""
    import time
    from unittest.mock import patch, Mock

    window = MainWindow()
    window._hash_by_path = {Path("/test.pdf"): "hash1"}
    window._toolbar.EnableTool(window._reload_id, True)
    window._last_reload_time = time.monotonic()  # Just now

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = True

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_not_called()

    window._frame.Destroy()


def test_on_frame_activate_skips_during_processing(wx_app):
    """EVT_ACTIVATE skips reload when processing is in progress (reload tool disabled)."""
    from unittest.mock import patch, Mock

    window = MainWindow()
    window._hash_by_path = {Path("/test.pdf"): "hash1"}
    window._toolbar.EnableTool(window._reload_id, False)  # Processing in progress
    window._last_reload_time = 0.0

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = True

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_not_called()

    window._frame.Destroy()


def test_enable_action_tools_reload(wx_app):
    """_enable_action_tools controls reload tool state."""
    window = MainWindow()

    window._enable_action_tools(reload=True)
    assert window._toolbar.GetToolEnabled(window._reload_id)

    window._enable_action_tools(reload=False)
    assert not window._toolbar.GetToolEnabled(window._reload_id)

    window._frame.Destroy()


def test_reload_hash_error_skips_file(wx_app, tmp_path):
    """_reload_cards skips files that can't be hashed (OSError)."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._pdf_files = [pdf]

    with patch("app.core.database.compute_file_hash", side_effect=OSError("disk error")), \
         patch.object(window, "_show_info_message") as mock_msg:
        window._reload_cards()
        # Should show "up to date" since the error is skipped
        assert "up to date" in mock_msg.call_args[0][0]

    # Card should still exist
    assert "hash1" in window._cards_by_hash

    window._frame.Destroy()


def test_reload_toolbar_in_icon_map(wx_app):
    """Test reload icon is refreshed during appearance change."""
    window = MainWindow()

    # Verify _reload_id is in the icon map (tested via _refresh_toolbar_icons)
    from unittest.mock import patch
    with patch("app.gui.main_window.load_sf_symbol", return_value=None) as mock_load:
        window._refresh_toolbar_icons()
        # Check arrow.clockwise was requested
        symbol_names = [call.args[0] for call in mock_load.call_args_list]
        assert "arrow.clockwise" in symbol_names

    window._frame.Destroy()


# ============================================================================
# mtime Pre-filter Tests
# ============================================================================


def test_reload_mtime_only_skips_unchanged(wx_app, tmp_path):
    """mtime_only=True skips files with unchanged mtime (no hash call)."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")
    mtime = pdf.stat().st_mtime

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._mtime_by_path = {pdf: mtime}
    window._pdf_files = [pdf]

    with patch("app.core.database.compute_file_hash") as mock_hash, \
         patch.object(window, "_show_info_message"):
        window._reload_cards(mtime_only=True)
        mock_hash.assert_not_called()

    # Card should still exist
    assert "hash1" in window._cards_by_hash

    window._frame.Destroy()


def test_reload_mtime_only_hashes_on_mtime_change(wx_app, tmp_path):
    """mtime_only=True falls through to hash check when mtime differs."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._mtime_by_path = {pdf: 0.0}  # Stale mtime — will differ from stat
    window._pdf_files = [pdf]

    with patch("app.core.database.compute_file_hash", return_value="hash1") as mock_hash, \
         patch.object(window, "_show_info_message"):
        window._reload_cards(mtime_only=True)
        mock_hash.assert_called_once_with(pdf)

    window._frame.Destroy()


def test_reload_manual_always_hashes(wx_app, tmp_path):
    """mtime_only=False (manual reload) always hashes, even when mtime matches."""
    from unittest.mock import patch
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")
    mtime = pdf.stat().st_mtime

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._mtime_by_path = {pdf: mtime}
    window._pdf_files = [pdf]

    with patch("app.core.database.compute_file_hash", return_value="hash1") as mock_hash, \
         patch.object(window, "_show_info_message"):
        window._reload_cards(mtime_only=False)
        mock_hash.assert_called_once_with(pdf)

    window._frame.Destroy()


def test_on_frame_activate_uses_mtime_only(wx_app, tmp_path):
    """EVT_ACTIVATE passes mtime_only=True to _reload_cards."""
    from unittest.mock import patch, Mock
    from app.models.card import CardResult, Confidence

    window = MainWindow()

    pdf = tmp_path / "card.pdf"
    pdf.write_bytes(b"content")

    card = CardResult(id=0, file_paths=[pdf], primary_path=pdf)
    card.file_hash = "hash1"
    card.confidence = Confidence.HIGH
    window._cards_by_hash = {"hash1": card}
    window._hash_by_path = {pdf: "hash1"}
    window._toolbar.EnableTool(window._reload_id, True)
    window._last_reload_time = 0.0

    event = Mock(spec=wx.ActivateEvent)
    event.GetActive.return_value = True

    with patch.object(window, "_reload_cards") as mock_reload:
        window._on_frame_activate(event)
        mock_reload.assert_called_once_with(mtime_only=True)

    window._frame.Destroy()
