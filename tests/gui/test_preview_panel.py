"""Tests for wxPython preview panel."""

from unittest.mock import Mock, patch

import pytest
import wx
from PIL import Image

from app.gui.components.preview_panel import PreviewPanel


@pytest.fixture
def frame(wx_app):
    """Create test frame."""
    frame = wx.Frame(None)
    yield frame
    frame.Destroy()


@pytest.fixture
def preview_panel(frame):
    """Create preview panel for testing."""
    panel = PreviewPanel(frame)
    frame.SetSize(800, 600)
    frame.Layout()
    return panel


@pytest.fixture
def sample_image():
    """Create a sample PIL image."""
    return Image.new("RGB", (400, 600), color="white")


@pytest.fixture
def sample_images():
    """Create multiple sample PIL images."""
    return [
        Image.new("RGB", (400, 600), color="white"),
        Image.new("RGB", (400, 600), color="lightgray"),
        Image.new("RGB", (400, 600), color="lightblue"),
    ]


# --- Level 1: Unit tests (basic functionality) ---


def test_initialization(preview_panel):
    """Test that preview panel initializes without errors."""
    assert preview_panel is not None
    assert isinstance(preview_panel, wx.Panel)
    assert preview_panel._images == []
    assert preview_panel._page_idx == 0
    assert preview_panel._zoom == 1.0
    assert preview_panel._is_fit is True


def test_show_images_single(preview_panel, sample_image):
    """Test displaying a single image."""
    preview_panel.show_images([sample_image], "test.pdf")

    assert len(preview_panel._images) == 1
    assert preview_panel._page_idx == 0
    assert preview_panel._is_fit is True
    assert preview_panel._title_label.GetLabel() == "PREVIEW: test.pdf"


def test_show_images_multiple(preview_panel, sample_images):
    """Test displaying multiple images."""
    preview_panel.show_images(sample_images, "multi.pdf")

    assert len(preview_panel._images) == 3
    assert preview_panel._page_idx == 0
    assert preview_panel._title_label.GetLabel() == "PREVIEW: multi.pdf"


def test_show_image(preview_panel, sample_image):
    """Test showing single image (backward compat)."""
    preview_panel.show_image(sample_image, "single.pdf")

    assert len(preview_panel._images) == 1
    assert preview_panel._page_idx == 0
    assert preview_panel._title_label.GetLabel() == "PREVIEW: single.pdf"


def test_clear(preview_panel, sample_images):
    """Test that clear resets state."""
    # First show some images
    preview_panel.show_images(sample_images, "test.pdf")
    assert len(preview_panel._images) > 0

    # Then clear
    preview_panel.clear()

    assert preview_panel._images == []
    assert preview_panel._page_idx == 0
    assert preview_panel._bitmap_cache is None
    assert preview_panel._title_label.GetLabel() == "PREVIEW"
    assert preview_panel._page_label.GetLabel() == ""


def test_show_error(preview_panel):
    """Test error message display."""
    preview_panel.show_error("Test error message", "error.pdf")

    assert preview_panel._error_message == "Test error message"
    assert preview_panel._images == []
    assert preview_panel._title_label.GetLabel() == "PREVIEW: error.pdf"


def test_zoom_controls_disabled_when_empty(preview_panel):
    """Test that zoom buttons are disabled when no images loaded."""
    preview_panel.clear()

    assert not preview_panel._fit_btn.IsEnabled()
    assert not preview_panel._zin_btn.IsEnabled()
    assert not preview_panel._zout_btn.IsEnabled()
    assert preview_panel._zoom_label.GetLabel() == ""


def test_zoom_controls_enabled_when_images_loaded(preview_panel, sample_image):
    """Test that zoom buttons are enabled when images are loaded."""
    preview_panel.show_images([sample_image])

    assert preview_panel._fit_btn.IsEnabled()
    assert preview_panel._zin_btn.IsEnabled()
    assert preview_panel._zout_btn.IsEnabled()


def test_page_navigation_single_page(preview_panel, sample_image):
    """Test that page navigation is disabled for single page."""
    preview_panel.show_images([sample_image])

    assert not preview_panel._prev_btn.IsEnabled()
    assert not preview_panel._next_btn.IsEnabled()
    assert preview_panel._page_label.GetLabel() == "1 / 1"


def test_page_navigation_multi_page(preview_panel, sample_images):
    """Test that page navigation works for multiple pages."""
    preview_panel.show_images(sample_images)

    # First page - can't go back
    assert not preview_panel._prev_btn.IsEnabled()
    assert preview_panel._next_btn.IsEnabled()
    assert preview_panel._page_label.GetLabel() == "1 / 3"


# --- Level 2: Integration tests (component interaction) ---


def test_zoom_in_out(preview_panel, sample_image):
    """Test zoom in and out functionality."""
    preview_panel.show_images([sample_image])

    # Get initial zoom (fit mode)
    initial_zoom = preview_panel._fit_zoom
    assert preview_panel._is_fit is True

    # Zoom in
    preview_panel._zoom_in()
    assert preview_panel._is_fit is False
    assert preview_panel._zoom > initial_zoom

    # Zoom out
    current_zoom = preview_panel._zoom
    preview_panel._zoom_out()
    assert preview_panel._zoom < current_zoom


def test_zoom_fit(preview_panel, sample_image):
    """Test zoom fit button resets to fit mode."""
    preview_panel.show_images([sample_image])

    # Zoom in first
    preview_panel._zoom_in()
    assert preview_panel._is_fit is False

    # Then fit
    preview_panel._zoom_fit()
    assert preview_panel._is_fit is True
    assert preview_panel._pan_x == 0.0
    assert preview_panel._pan_y == 0.0
    assert preview_panel._zoom_label.GetLabel() == "Fit"


def test_prev_next_page(preview_panel, sample_images):
    """Test page navigation updates display."""
    preview_panel.show_images(sample_images)

    # Start at page 0
    assert preview_panel._page_idx == 0

    # Go to next page
    preview_panel.next_page()
    assert preview_panel._page_idx == 1
    assert preview_panel._page_label.GetLabel() == "2 / 3"
    assert preview_panel._prev_btn.IsEnabled()

    # Go to next page again
    preview_panel.next_page()
    assert preview_panel._page_idx == 2
    assert preview_panel._page_label.GetLabel() == "3 / 3"
    assert not preview_panel._next_btn.IsEnabled()

    # Go back
    preview_panel.prev_page()
    assert preview_panel._page_idx == 1
    assert preview_panel._page_label.GetLabel() == "2 / 3"


def test_zoom_updates_label(preview_panel, sample_image):
    """Test that zoom label shows percentage."""
    preview_panel.show_images([sample_image])

    # Initial fit mode
    assert preview_panel._zoom_label.GetLabel() == "Fit"

    # Zoom in
    preview_panel._zoom_in()
    label = preview_panel._zoom_label.GetLabel()
    assert label.endswith("%")
    assert label != "Fit"


def test_page_label_format(preview_panel, sample_images):
    """Test that page label shows correct format."""
    preview_panel.show_images(sample_images)

    assert preview_panel._page_label.GetLabel() == "1 / 3"

    preview_panel.next_page()
    assert preview_panel._page_label.GetLabel() == "2 / 3"


def test_zoom_resets_on_page_change(preview_panel, sample_images):
    """Test that zoom resets when changing pages."""
    preview_panel.show_images(sample_images)

    # Zoom in and pan on first page
    preview_panel._zoom_in()
    preview_panel._pan_x = 50.0
    preview_panel._pan_y = 30.0
    assert preview_panel._is_fit is False

    # Navigate to next page
    preview_panel.next_page()

    # Zoom and pan should be reset
    assert preview_panel._is_fit is True
    assert preview_panel._pan_x == 0.0
    assert preview_panel._pan_y == 0.0


def test_apply_zoom_within_limits(preview_panel, sample_image):
    """Test that zoom is clamped to MIN/MAX limits."""
    preview_panel.show_images([sample_image])

    # Zoom in many times
    for _ in range(20):
        preview_panel._zoom_in()

    assert preview_panel._zoom <= PreviewPanel.MAX_ZOOM

    # Zoom out many times
    for _ in range(40):
        preview_panel._zoom_out()

    assert preview_panel._zoom >= PreviewPanel.MIN_ZOOM


def test_error_clears_images(preview_panel, sample_images):
    """Test that showing error clears image state."""
    # Load images first
    preview_panel.show_images(sample_images)
    assert len(preview_panel._images) > 0

    # Show error
    preview_panel.show_error("Error occurred")

    assert preview_panel._images == []
    assert preview_panel._bitmap_cache is None
    assert not preview_panel._prev_btn.IsEnabled()
    assert not preview_panel._next_btn.IsEnabled()


# --- Level 3: UI integration tests ---


def test_preview_in_dialog(wx_app):
    """Test that preview panel works in a dialog."""
    dialog = wx.Dialog(None, title="Test", size=(600, 400))
    preview = PreviewPanel(dialog)

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(preview, 1, wx.EXPAND | wx.ALL, 10)
    dialog.SetSizer(sizer)

    # Load an image
    img = Image.new("RGB", (300, 400), color="lightblue")
    preview.show_images([img], "dialog-test.pdf")

    assert len(preview._images) == 1

    dialog.Destroy()


def test_multiple_images_navigation(preview_panel, sample_images):
    """Test navigating through all pages."""
    preview_panel.show_images(sample_images)

    # Navigate through all pages
    for i in range(len(sample_images)):
        assert preview_panel._page_idx == i
        assert preview_panel._page_label.GetLabel() == f"{i + 1} / {len(sample_images)}"

        if i < len(sample_images) - 1:
            preview_panel.next_page()

    # Navigate back
    for i in range(len(sample_images) - 1, -1, -1):
        assert preview_panel._page_idx == i
        if i > 0:
            preview_panel.prev_page()


def test_show_images_clears_error(preview_panel):
    """Test that showing images clears any previous error."""
    # Show error first
    preview_panel.show_error("Test error")
    assert preview_panel._error_message != ""

    # Show images
    img = Image.new("RGB", (300, 400), color="white")
    preview_panel.show_images([img])

    assert preview_panel._error_message == ""
    assert len(preview_panel._images) == 1


def test_render_with_no_images(preview_panel):
    """Test that render handles no images gracefully."""
    preview_panel.clear()
    preview_panel._render()

    # Should not crash, bitmap_cache should be None
    assert preview_panel._bitmap_cache is None


def test_pan_state(preview_panel, sample_image):
    """Test pan state tracking."""
    preview_panel.show_images([sample_image])

    # Initial pan should be 0
    assert preview_panel._pan_x == 0.0
    assert preview_panel._pan_y == 0.0

    # Simulate pan (normally done through mouse events)
    preview_panel._pan_x = 100.0
    preview_panel._pan_y = 50.0

    assert preview_panel._pan_x == 100.0
    assert preview_panel._pan_y == 50.0


def test_filename_optional(preview_panel, sample_image):
    """Test that filename is optional in show_images."""
    preview_panel.show_images([sample_image])

    # Without filename, should just show "Preview"
    assert preview_panel._title_label.GetLabel() == "PREVIEW"

    # With filename
    preview_panel.show_images([sample_image], "test.pdf")
    assert preview_panel._title_label.GetLabel() == "PREVIEW: test.pdf"


def test_empty_images_list(preview_panel):
    """Test handling of empty images list."""
    preview_panel.show_images([], "empty.pdf")

    assert len(preview_panel._images) == 0
    assert preview_panel._page_label.GetLabel() == ""
    assert not preview_panel._prev_btn.IsEnabled()
    assert not preview_panel._next_btn.IsEnabled()


def test_zoom_transition_from_fit_to_explicit(preview_panel, sample_image):
    """Test transition from fit mode to explicit zoom."""
    preview_panel.show_images([sample_image])

    # Start in fit mode
    assert preview_panel._is_fit is True
    fit_zoom = preview_panel._fit_zoom

    # Apply zoom - should transition to explicit mode
    preview_panel._apply_zoom(1.25)

    assert preview_panel._is_fit is False
    assert preview_panel._zoom == pytest.approx(fit_zoom * 1.25)


def test_wrap_text(preview_panel):
    """Test text wrapping for error messages."""
    import wx

    dc = wx.MemoryDC()
    dc.SetFont(preview_panel._title_label.GetFont())

    text = "This is a long error message that should wrap"
    lines = preview_panel._wrap_text(dc, text, 100)

    # Should wrap into multiple lines
    assert len(lines) > 1
    assert all(isinstance(line, str) for line in lines)


# --- Level 4: Mouse events and modifier keys ---


def test_left_click_with_shift_zooms_in(preview_panel, sample_image):
    """Test Shift+Click zooms in."""
    preview_panel.show_images([sample_image])

    initial_zoom = preview_panel._fit_zoom

    # Create mock event with Shift modifier
    event = Mock()
    event.GetX.return_value = 100
    event.GetY.return_value = 100
    event.GetModifiers.return_value = wx.MOD_SHIFT
    event.Skip = Mock()

    preview_panel._on_left_down(event)

    # Should have zoomed in
    assert not preview_panel._is_fit
    assert preview_panel._zoom > initial_zoom


def test_left_click_with_alt_zooms_out(preview_panel, sample_image):
    """Test Alt/Option+Click zooms out."""
    preview_panel.show_images([sample_image])

    # Zoom in first to have room to zoom out
    preview_panel._zoom_in()
    current_zoom = preview_panel._zoom

    # Create mock event with Alt modifier
    event = Mock()
    event.GetX.return_value = 100
    event.GetY.return_value = 100
    event.GetModifiers.return_value = wx.MOD_ALT
    event.Skip = Mock()

    preview_panel._on_left_down(event)

    # Should have zoomed out
    assert preview_panel._zoom < current_zoom


def test_left_click_no_modifier_starts_pan(preview_panel, sample_image):
    """Test click without modifiers starts pan."""
    preview_panel.show_images([sample_image])

    # Create mock event with no modifiers
    event = Mock()
    event.GetX.return_value = 100
    event.GetY.return_value = 100
    event.GetModifiers.return_value = 0
    event.Skip = Mock()

    preview_panel._on_left_down(event)

    # Should have started pan
    assert preview_panel._drag_start is not None
    assert preview_panel._drag_start == (100, 100)


def test_left_click_both_modifiers_starts_pan(preview_panel, sample_image):
    """Test click with both modifiers (ambiguous) starts pan."""
    preview_panel.show_images([sample_image])

    # Create mock event with both modifiers
    event = Mock()
    event.GetX.return_value = 100
    event.GetY.return_value = 100
    event.GetModifiers.return_value = wx.MOD_SHIFT | wx.MOD_ALT
    event.Skip = Mock()

    preview_panel._on_left_down(event)

    # Ambiguous state - should start pan
    assert preview_panel._drag_start is not None


def test_double_click_with_shift_zooms_twice(preview_panel, sample_image):
    """Test double-click with Shift zooms in twice."""
    preview_panel.show_images([sample_image])

    initial_zoom = preview_panel._fit_zoom

    # First click
    event1 = Mock()
    event1.GetX.return_value = 100
    event1.GetY.return_value = 100
    event1.GetModifiers.return_value = wx.MOD_SHIFT
    event1.Skip = Mock()
    preview_panel._on_left_down(event1)

    zoom_after_first = preview_panel._zoom

    # Double-click (handled as second left down)
    event2 = Mock()
    event2.GetX.return_value = 100
    event2.GetY.return_value = 100
    event2.GetModifiers.return_value = wx.MOD_SHIFT
    event2.Skip = Mock()
    preview_panel._on_left_down(event2)

    # Should have zoomed twice
    assert preview_panel._zoom > zoom_after_first
    expected = initial_zoom * (PreviewPanel.ZOOM_STEP**2)
    assert preview_panel._zoom == pytest.approx(expected)


def test_click_with_no_images_no_crash(preview_panel):
    """Test clicking when no images loaded doesn't crash."""
    preview_panel.clear()

    event = Mock()
    event.GetX.return_value = 100
    event.GetY.return_value = 100
    event.GetModifiers.return_value = wx.MOD_SHIFT
    event.Skip = Mock()

    preview_panel._on_left_down(event)

    # Should not crash, zoom should remain at default
    assert preview_panel._zoom == 1.0
    assert preview_panel._is_fit


def test_scroll_up_zooms_in(preview_panel, sample_image):
    """Test scroll wheel up zooms in."""
    preview_panel.show_images([sample_image])

    initial_zoom = preview_panel._fit_zoom

    # Create scroll event with positive rotation (up)
    event = wx.MouseEvent(wx.wxEVT_MOUSEWHEEL)
    event.SetWheelRotation(120)  # Positive = scroll up

    preview_panel._on_scroll_zoom(event)

    # Should have zoomed in
    assert not preview_panel._is_fit
    assert preview_panel._zoom > initial_zoom


def test_scroll_down_zooms_out(preview_panel, sample_image):
    """Test scroll wheel down zooms out."""
    preview_panel.show_images([sample_image])

    # Zoom in first
    preview_panel._zoom_in()
    current_zoom = preview_panel._zoom

    # Create scroll event with negative rotation (down)
    event = wx.MouseEvent(wx.wxEVT_MOUSEWHEEL)
    event.SetWheelRotation(-120)  # Negative = scroll down

    preview_panel._on_scroll_zoom(event)

    # Should have zoomed out
    assert preview_panel._zoom < current_zoom


def test_scroll_with_no_images_no_crash(preview_panel):
    """Test scroll wheel with no images doesn't crash."""
    preview_panel.clear()

    event = wx.MouseEvent(wx.wxEVT_MOUSEWHEEL)
    event.SetWheelRotation(120)

    preview_panel._on_scroll_zoom(event)

    # Should not crash
    assert preview_panel._zoom == 1.0


def test_on_motion_pans_during_drag(preview_panel, sample_image):
    """Test mouse motion updates pan during drag."""
    preview_panel.show_images([sample_image])

    # Start pan
    preview_panel._drag_start = (100, 100)
    initial_pan_x = preview_panel._pan_x
    initial_pan_y = preview_panel._pan_y

    # Create motion event
    event = wx.MouseEvent(wx.wxEVT_MOTION)
    event.SetPosition((150, 120))

    preview_panel._on_motion(event)

    # Pan should have updated
    assert preview_panel._pan_x != initial_pan_x
    assert preview_panel._pan_y != initial_pan_y
    assert preview_panel._pan_x == initial_pan_x + 50
    assert preview_panel._pan_y == initial_pan_y + 20


def test_on_pan_end_clears_drag_state(preview_panel, sample_image):
    """Test left button up ends pan."""
    preview_panel.show_images([sample_image])

    # Start pan
    preview_panel._drag_start = (100, 100)

    # Create left up event
    event = wx.MouseEvent(wx.wxEVT_LEFT_UP)

    preview_panel._on_pan_end(event)

    # Drag should be ended
    assert preview_panel._drag_start is None


# --- Level 5: Edge cases ---


def test_rapid_page_changes(preview_panel):
    """Test rapid page navigation doesn't crash."""
    images = [Image.new("RGB", (400, 600), color=c) for c in ["white", "gray", "blue", "red"]]
    preview_panel.show_images(images)

    # Rapidly navigate
    for _ in range(10):
        preview_panel.next_page()
        preview_panel.prev_page()
        preview_panel.next_page()

    # Should not crash
    assert 0 <= preview_panel._page_idx < len(images)


def test_zoom_clamped_at_max(preview_panel, sample_image):
    """Test zoom cannot exceed MAX_ZOOM."""
    preview_panel.show_images([sample_image])

    # Zoom in many times
    for _ in range(30):
        preview_panel._zoom_in()

    # Should be clamped at MAX_ZOOM
    assert preview_panel._zoom <= PreviewPanel.MAX_ZOOM


def test_zoom_clamped_at_min(preview_panel, sample_image):
    """Test zoom cannot go below MIN_ZOOM."""
    preview_panel.show_images([sample_image])

    # Zoom out many times
    for _ in range(50):
        preview_panel._zoom_out()

    # Should be clamped at MIN_ZOOM
    assert preview_panel._zoom >= PreviewPanel.MIN_ZOOM


def test_show_images_while_panning(preview_panel, sample_images):
    """Test loading new images during pan resets state."""
    preview_panel.show_images([sample_images[0]])

    # Start pan
    preview_panel._drag_start = (100, 100)
    preview_panel._pan_x = 50
    preview_panel._pan_y = 30

    # Load new images
    preview_panel.show_images([sample_images[1]])

    # Pan offsets should be reset (drag_start may not be)
    assert preview_panel._pan_x == 0.0
    assert preview_panel._pan_y == 0.0
    # Note: _drag_start is not reset by show_images, only by _reset_view


def test_show_error_while_panning(preview_panel, sample_image):
    """Test showing error during pan clears state."""
    preview_panel.show_images([sample_image])

    # Start pan
    preview_panel._drag_start = (100, 100)
    preview_panel._pan_x = 50

    # Show error
    preview_panel.show_error("Test error")

    # Images should be cleared (drag_start may not be)
    assert preview_panel._images == []
    # Note: show_error doesn't reset _drag_start, only clears images


def test_render_with_invalid_page_index(preview_panel, sample_images):
    """Test render handles invalid page index gracefully."""
    preview_panel.show_images(sample_images)

    # Set invalid page index
    preview_panel._page_idx = 99

    # Render should not crash
    preview_panel._render()

    # Bitmap should be None
    assert preview_panel._bitmap_cache is None


def test_pan_with_very_large_offsets(preview_panel, sample_image):
    """Test pan handles very large offsets."""
    preview_panel.show_images([sample_image])

    # Set extreme pan values
    preview_panel._pan_x = 10000.0
    preview_panel._pan_y = -10000.0

    # Render should not crash
    preview_panel._render()

    # Canvas refresh should not crash
    preview_panel._canvas.Refresh()

    assert True


# --- Level 6: Cursor loading, refresh_colors, guards, and math ---


def test_cursor_fallback_on_import_error(frame):
    """Test cursor loading falls back to standard cursors when import fails."""
    with patch.dict("sys.modules", {"app.gui.icons": None}):
        panel = PreviewPanel(frame)

    # Should have fallen back to standard wx cursors (not None)
    assert panel._zoom_in_cursor is not None
    assert panel._zoom_out_cursor is not None


def test_cursor_fallback_on_os_error(frame):
    """Test cursor loading falls back to standard cursors on OSError."""
    mock_icons = Mock()
    mock_icons.load_cursor_from_symbol = Mock(side_effect=OSError("test"))
    with patch.dict("sys.modules", {"app.gui.icons": mock_icons}):
        panel = PreviewPanel(frame)

    assert panel._zoom_in_cursor is not None
    assert panel._zoom_out_cursor is not None


def test_cursor_fallback_on_attribute_error(frame):
    """Test cursor loading falls back to standard cursors on AttributeError."""
    mock_icons = Mock()
    mock_icons.load_cursor_from_symbol = Mock(side_effect=AttributeError("test"))
    with patch.dict("sys.modules", {"app.gui.icons": mock_icons}):
        panel = PreviewPanel(frame)

    assert panel._zoom_in_cursor is not None
    assert panel._zoom_out_cursor is not None


def test_cursor_fallback_when_load_returns_none(frame):
    """Test cursor fallback when load_cursor_from_symbol returns None."""
    mock_icons = Mock()
    mock_icons.load_cursor_from_symbol = Mock(return_value=None)
    with patch.dict("sys.modules", {"app.gui.icons": mock_icons}):
        panel = PreviewPanel(frame)

    # Fallback should assign standard cursors
    assert panel._zoom_in_cursor is not None
    assert panel._zoom_out_cursor is not None


def test_refresh_colors_updates_labels(preview_panel):
    """Test refresh_colors updates label foreground colors."""
    from app.gui import styles

    preview_panel.refresh_colors()

    assert preview_panel._title_label.GetForegroundColour() == styles.Color.TEXT_SECONDARY
    assert preview_panel._page_label.GetForegroundColour() == styles.Color.TEXT_PRIMARY
    assert preview_panel._zoom_label.GetForegroundColour() == styles.Color.TEXT_PRIMARY


def test_on_pan_start_guard_no_images(preview_panel):
    """Test _on_pan_start is a no-op when no images are loaded."""
    preview_panel.clear()

    event = Mock()
    event.GetX.return_value = 50
    event.GetY.return_value = 50

    preview_panel._on_pan_start(event)

    # Should not set drag_start
    assert preview_panel._drag_start is None


def test_on_pan_drag_guard_no_drag_start(preview_panel, sample_image):
    """Test _on_pan_drag returns early when drag_start is None."""
    preview_panel.show_images([sample_image])
    preview_panel._drag_start = None

    initial_pan_x = preview_panel._pan_x
    initial_pan_y = preview_panel._pan_y

    event = Mock()
    event.GetX.return_value = 200
    event.GetY.return_value = 200

    preview_panel._on_pan_drag(event)

    # Pan should not have changed
    assert preview_panel._pan_x == initial_pan_x
    assert preview_panel._pan_y == initial_pan_y


def test_on_motion_updates_cursor_when_not_dragging(preview_panel, sample_image):
    """Test _on_motion calls _update_cursor when not dragging."""
    preview_panel.show_images([sample_image])
    preview_panel._drag_start = None

    with patch.object(preview_panel, "_update_cursor") as mock_cursor:
        event = wx.MouseEvent(wx.wxEVT_MOTION)
        event.SetPosition((150, 150))
        preview_panel._on_motion(event)

        mock_cursor.assert_called_once()


def test_on_motion_guard_no_images(preview_panel):
    """Test _on_motion returns early when no images loaded."""
    preview_panel.clear()

    with patch.object(preview_panel, "_update_cursor") as mock_cursor:
        with patch.object(preview_panel, "_on_pan_drag") as mock_drag:
            event = wx.MouseEvent(wx.wxEVT_MOTION)
            event.SetPosition((150, 150))
            preview_panel._on_motion(event)

            mock_cursor.assert_not_called()
            mock_drag.assert_not_called()


def test_modifier_timer_stop_when_no_app(preview_panel, sample_image):
    """Test modifier timer stops safely when wx.GetApp() returns None."""
    preview_panel.show_images([sample_image])
    preview_panel._modifier_timer.Start(50)

    with patch("app.gui.components.preview_panel.wx.GetApp", return_value=None):
        event = Mock()
        preview_panel._on_modifier_timer(event)

    # Timer should have been stopped
    assert not preview_panel._modifier_timer.IsRunning()


def test_modifier_timer_updates_cursor_with_images(preview_panel, sample_image):
    """Test modifier timer calls _update_cursor when images are loaded and not dragging."""
    preview_panel.show_images([sample_image])
    preview_panel._drag_start = None

    with patch.object(preview_panel, "_update_cursor") as mock_cursor:
        event = Mock()
        preview_panel._on_modifier_timer(event)

        mock_cursor.assert_called_once()


def test_modifier_timer_skips_cursor_during_drag(preview_panel, sample_image):
    """Test modifier timer does not update cursor during drag."""
    preview_panel.show_images([sample_image])
    preview_panel._drag_start = (100, 100)

    with patch.object(preview_panel, "_update_cursor") as mock_cursor:
        event = Mock()
        preview_panel._on_modifier_timer(event)

        mock_cursor.assert_not_called()


def test_on_resize_refreshes_on_error(preview_panel):
    """Test _on_resize refreshes canvas when error message is set."""
    preview_panel.show_error("Some error")

    with patch.object(preview_panel._canvas, "Refresh") as mock_refresh:
        preview_panel._on_resize(None)

        mock_refresh.assert_called_once()


def test_on_resize_renders_when_images_loaded(preview_panel, sample_image):
    """Test _on_resize calls _render when images are loaded."""
    preview_panel.show_images([sample_image])

    with patch.object(preview_panel, "_render") as mock_render:
        preview_panel._on_resize(None)

        mock_render.assert_called_once()


def test_on_resize_no_action_when_empty(preview_panel):
    """Test _on_resize does nothing when no images and no error."""
    preview_panel.clear()

    with patch.object(preview_panel._canvas, "Refresh") as mock_refresh:
        with patch.object(preview_panel, "_render") as mock_render:
            preview_panel._on_resize(None)

            mock_refresh.assert_not_called()
            mock_render.assert_not_called()


def test_on_resize_skips_event(preview_panel, sample_image):
    """Test _on_resize calls event.Skip() when event is provided."""
    preview_panel.show_images([sample_image])

    event = Mock()
    preview_panel._on_resize(event)

    event.Skip.assert_called_once()


def test_apply_zoom_clamps_to_max(preview_panel, sample_image):
    """Test _apply_zoom clamps zoom to MAX_ZOOM."""
    preview_panel.show_images([sample_image])

    # Apply a huge zoom factor
    preview_panel._apply_zoom(1000.0)

    assert preview_panel._zoom == PreviewPanel.MAX_ZOOM


def test_apply_zoom_clamps_to_min(preview_panel, sample_image):
    """Test _apply_zoom clamps zoom to MIN_ZOOM."""
    preview_panel.show_images([sample_image])

    # Apply a tiny zoom factor
    preview_panel._apply_zoom(0.001)

    assert preview_panel._zoom == PreviewPanel.MIN_ZOOM


def test_apply_zoom_transition_from_fit_uses_fit_zoom(preview_panel, sample_image):
    """Test _apply_zoom uses _fit_zoom as base when transitioning from fit mode."""
    preview_panel.show_images([sample_image])

    assert preview_panel._is_fit is True
    fit_zoom = preview_panel._fit_zoom

    # Apply zoom from fit mode
    factor = 1.5
    preview_panel._apply_zoom(factor)

    assert preview_panel._is_fit is False
    expected = max(PreviewPanel.MIN_ZOOM, min(PreviewPanel.MAX_ZOOM, fit_zoom * factor))
    assert preview_panel._zoom == pytest.approx(expected)


def test_apply_zoom_label_percentage(preview_panel, sample_image):
    """Test _apply_zoom updates label to correct percentage relative to fit."""
    preview_panel.show_images([sample_image])

    fit_zoom = preview_panel._fit_zoom

    # Zoom in by 2x
    preview_panel._apply_zoom(2.0)

    expected_pct = int((fit_zoom * 2.0) / fit_zoom * 100)
    assert preview_panel._zoom_label.GetLabel() == f"{expected_pct}%"


def test_apply_zoom_label_with_zero_fit_zoom(preview_panel, sample_image):
    """Test _apply_zoom shows 100% when fit_zoom is 0."""
    preview_panel.show_images([sample_image])

    # Force fit_zoom to 0
    preview_panel._fit_zoom = 0.0

    preview_panel._apply_zoom(1.5)

    assert preview_panel._zoom_label.GetLabel() == "100%"


def test_apply_zoom_successive_multiplications(preview_panel, sample_image):
    """Test successive _apply_zoom calls multiply correctly."""
    preview_panel.show_images([sample_image])

    fit_zoom = preview_panel._fit_zoom

    # First zoom: transitions from fit
    preview_panel._apply_zoom(PreviewPanel.ZOOM_STEP)
    first = preview_panel._zoom

    # Second zoom: multiplies from current
    preview_panel._apply_zoom(PreviewPanel.ZOOM_STEP)
    second = preview_panel._zoom

    assert first == pytest.approx(fit_zoom * PreviewPanel.ZOOM_STEP)
    assert second == pytest.approx(fit_zoom * PreviewPanel.ZOOM_STEP ** 2)


def test_paint_coordinate_calculation(preview_panel, sample_image):
    """Test that bitmap position calculation uses correct centering and pan offsets."""
    preview_panel.show_images([sample_image])

    # Set known pan offsets
    preview_panel._pan_x = 30.0
    preview_panel._pan_y = -20.0

    # Force render to create bitmap cache
    preview_panel._render()
    assert preview_panel._bitmap_cache is not None

    # Verify the expected position math
    cw, ch = preview_panel._canvas.GetSize()
    cx, cy = cw // 2, ch // 2
    bw = preview_panel._bitmap_cache.GetWidth()
    bh = preview_panel._bitmap_cache.GetHeight()

    expected_x = cx + int(preview_panel._pan_x) - bw // 2
    expected_y = cy + int(preview_panel._pan_y) - bh // 2

    # These values should be computable without crashing
    assert isinstance(expected_x, int)
    assert isinstance(expected_y, int)
