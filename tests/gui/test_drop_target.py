"""Tests for drop target overlay and file drop target."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import wx

from app.gui.components.drop_target import (
    DropOverlay,
    FileDropTarget,
    load_drop_background,
)

# --- load_drop_background() ---


def test_load_drop_background_returns_none_when_image_missing():
    """Returns None when the background image file does not exist."""
    with patch("app.gui.components.drop_target.get_runtime_content_path") as mock_path:
        fake_path = MagicMock()
        fake_path.exists.return_value = False
        mock_path.return_value = fake_path
        result = load_drop_background()
    assert result is None


def test_load_drop_background_returns_none_on_exception():
    """Returns None when any exception occurs during loading."""
    with patch(
        "app.gui.components.drop_target.get_runtime_content_path",
        side_effect=RuntimeError("boom"),
    ):
        result = load_drop_background()
    assert result is None


# --- DropOverlay ---


@pytest.fixture
def overlay(wx_frame):
    """Create a DropOverlay with load_drop_background patched to None."""
    with patch("app.gui.components.drop_target.load_drop_background", return_value=None):
        ov = DropOverlay(wx_frame)
    return ov


class TestDropOverlaySetDragActive:
    """Tests for DropOverlay.set_drag_active()."""

    def test_early_return_when_state_unchanged(self, overlay):
        """Does not call Refresh when drag state is already the same."""
        assert overlay._drag_active is False
        with patch.object(overlay, "Refresh") as mock_refresh:
            overlay.set_drag_active(False)
            mock_refresh.assert_not_called()

    def test_sets_state_and_refreshes(self, overlay):
        """Sets the drag state and calls Refresh when state changes."""
        with patch.object(overlay, "Refresh") as mock_refresh:
            overlay.set_drag_active(True)
            assert overlay._drag_active is True
            mock_refresh.assert_called_once()


class TestDropOverlayScaleBg:
    """Tests for DropOverlay._scale_bg()."""

    def test_cache_hit_returns_cached_bitmap(self, overlay):
        """Returns the cached bitmap when target size matches cache."""
        sentinel = wx.Bitmap(1, 1)
        overlay._bg_source = wx.Bitmap(100, 100)
        overlay._bg_scaled = sentinel
        overlay._bg_cache_size = (200, 200)

        result = overlay._scale_bg(200, 200)
        assert result is sentinel

    def test_returns_none_when_source_is_none(self, overlay):
        """Returns None when _bg_source is None."""
        assert overlay._bg_source is None
        result = overlay._scale_bg(200, 200)
        assert result is None

    def test_returns_none_for_zero_size_target(self, overlay):
        """Returns None when target width or height is zero."""
        overlay._bg_source = wx.Bitmap(100, 100)

        assert overlay._scale_bg(0, 200) is None
        assert overlay._scale_bg(200, 0) is None
        assert overlay._scale_bg(0, 0) is None


# --- FileDropTarget ---


class TestFileDropTargetOnDropFiles:
    """Tests for FileDropTarget.OnDropFiles()."""

    def test_empty_list_returns_false(self):
        """Returns False when filenames list is empty."""
        callback = MagicMock()
        target = FileDropTarget(on_drop=callback)
        result = target.OnDropFiles(0, 0, [])
        assert result is False
        callback.assert_not_called()

    def test_converts_filenames_to_paths_and_calls_callback(self):
        """Converts string filenames to Path objects and schedules callback."""
        callback = MagicMock()
        target = FileDropTarget(on_drop=callback)

        with patch("app.gui.components.drop_target.wx.CallAfter") as mock_call_after:
            result = target.OnDropFiles(0, 0, ["/tmp/a.pdf", "/tmp/b.pdf"])

        assert result is True
        mock_call_after.assert_called_once_with(callback, [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")])
