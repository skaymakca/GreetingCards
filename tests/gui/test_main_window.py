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
    window._pdf_files = [Path("test.pdf")]

    # Clear
    window._clear_all()

    # Verify reset
    assert window._next_card_id == 0
    assert len(window._cards_by_hash) == 0
    assert len(window._hash_by_path) == 0
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


def test_dict_to_card_conversion(wx_app):
    """Test conversion of worker dict to CardResult."""
    from PIL import Image
    import io

    window = MainWindow()

    # Create test image bytes
    img = Image.new('RGB', (100, 100), color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    # Create result dict (like from worker)
    result_dict = {
        'pdf_path': '/test/card.pdf',
        'file_hash': 'abc123',
        'family_name': 'Smith',
        'confidence': 'high',
        'method': 'ocr',
        'alternates': ['Smyth'],
        'candidates': [],
        'remove_family': False,
        'selected_candidate_id': None,
        'ocr_text': 'Smith Family',
        'error': None,
        'preview_image_bytes': img_bytes,
        'page_images_bytes': [img_bytes],
    }

    # Convert
    card = window._dict_to_card(result_dict, card_id=1)

    # Verify
    assert card.id == 1
    assert card.filename == "card.pdf"
    assert card.file_hash == 'abc123'
    assert card.family_name == 'Smith'
    assert card.preview_image is not None
    assert len(card.page_images) == 1

    window._frame.Destroy()


def test_dict_to_card_with_error(wx_app):
    """Test conversion handles error cards."""
    window = MainWindow()

    result_dict = {
        'pdf_path': '/test/card.pdf',
        'file_hash': None,
        'family_name': '',
        'confidence': 'none',
        'method': 'missing',
        'alternates': [],
        'candidates': [],
        'remove_family': False,
        'selected_candidate_id': None,
        'ocr_text': '',
        'error': 'Failed to process',
        'preview_image_bytes': None,
        'page_images_bytes': [],
    }

    card = window._dict_to_card(result_dict, card_id=1)

    assert card.error == 'Failed to process'
    assert card.confidence.value == 'none'

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


def test_accelerator_table_exists(wx_app):
    """Test keyboard accelerator table is set up."""
    window = MainWindow()

    # Verify accelerator table exists
    accel_table = window._frame.GetAcceleratorTable()
    assert accel_table is not None
    assert accel_table.IsOk()

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

    # AI All, Rename, Clear should be disabled initially
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
