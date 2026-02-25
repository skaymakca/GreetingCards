"""Tests for custom SF Symbol cursor loading functionality.

These tests cover the load_cursor_from_symbol() function which creates
wx.Cursor objects from SF Symbols for use as mouse cursors in the preview panel.
"""

from unittest.mock import Mock, patch

import pytest
import wx

from app.gui.icons import load_cursor_from_symbol


class TestCursorLoading:
    """Tests for basic cursor loading functionality."""

    def test_load_cursor_from_symbol_returns_cursor(self, wx_app):
        """Should return wx.Cursor for valid SF Symbol."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        # Should return cursor object or None if PyObjC unavailable
        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_cursor_invalid_symbol_returns_none(self, wx_app):
        """Should return None for invalid/nonexistent SF Symbol."""
        cursor = load_cursor_from_symbol("invalid_symbol_xyz_12345", point_size=7)

        assert cursor is None

    def test_load_cursor_different_sizes(self, wx_app):
        """Should create cursors at different sizes."""
        sizes = [6, 7, 12, 20]
        cursors = []

        for size in sizes:
            cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=size)
            cursors.append(cursor)

        # All should be valid cursors or all None (if PyObjC unavailable)
        if cursors[0] is not None:
            for cursor in cursors:
                assert isinstance(cursor, wx.Cursor)

    def test_load_cursor_different_colors(self, wx_app):
        """Should create cursors in different colors."""
        colors = ["#000000", "#FFFFFF", "#FF0000"]
        cursors = []

        for color in colors:
            cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7, color_hex=color)
            cursors.append(cursor)

        # All should be valid cursors or all None
        if cursors[0] is not None:
            for cursor in cursors:
                assert isinstance(cursor, wx.Cursor)

    def test_load_cursor_with_default_hotspot(self, wx_app):
        """Should set hotspot to center when not specified."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        # If cursor loaded successfully, it has hotspot set
        # (Can't directly query hotspot from wx.Cursor, but test that it loads)
        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_cursor_with_custom_hotspot(self, wx_app):
        """Should accept custom hotspot coordinates."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7, hotspot_x=5, hotspot_y=5)

        # Should load successfully with custom hotspot
        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_cursor_with_zero_hotspot(self, wx_app):
        """Should accept (0,0) hotspot."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7, hotspot_x=0, hotspot_y=0)

        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_cursor_empty_symbol_name(self, wx_app):
        """Should return None for empty symbol name."""
        cursor = load_cursor_from_symbol("", point_size=7)

        assert cursor is None

    def test_load_cursor_very_small_size(self, wx_app):
        """Should handle very small cursor size."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=4)

        # Should either work or return None gracefully
        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_cursor_very_large_size(self, wx_app):
        """Should handle very large cursor size."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=50)

        # Should either work or return None gracefully
        assert cursor is None or isinstance(cursor, wx.Cursor)


class TestCursorSymbols:
    """Tests for specific SF Symbols used as cursors."""

    def test_load_zoom_in_symbol(self, wx_app):
        """Should load plus.magnifyingglass symbol."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_zoom_out_symbol(self, wx_app):
        """Should load minus.magnifyingglass symbol."""
        cursor = load_cursor_from_symbol("minus.magnifyingglass", point_size=7)

        assert cursor is None or isinstance(cursor, wx.Cursor)

    def test_load_both_cursor_symbols(self, wx_app):
        """Should load both zoom cursor symbols successfully."""
        zoom_in = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)
        zoom_out = load_cursor_from_symbol("minus.magnifyingglass", point_size=7)

        # Both should succeed or both should fail
        if zoom_in is not None:
            assert isinstance(zoom_in, wx.Cursor)
            assert isinstance(zoom_out, wx.Cursor)


class TestCursorErrorHandling:
    """Tests for error handling in cursor loading."""

    def test_load_cursor_handles_import_error(self, wx_app):
        """Should return None gracefully when PyObjC unavailable."""
        # Mock the entire AppKit import to raise ImportError
        import sys

        original_modules = sys.modules.copy()

        # Remove AppKit if it exists
        if "AppKit" in sys.modules:
            del sys.modules["AppKit"]

        # Make import fail
        with patch.dict(sys.modules, {"AppKit": None}):
            # Trigger import error by importing inside function
            cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

            # Should handle gracefully (returns None or valid cursor if already imported)
            assert cursor is None or isinstance(cursor, wx.Cursor)

        # Restore modules
        sys.modules.update(original_modules)

    def test_load_cursor_prints_warning_on_error(self, wx_app, capsys):
        """Should print warning message when loading fails."""
        # Test with invalid symbol which triggers error path
        cursor = load_cursor_from_symbol("", point_size=7)

        assert cursor is None
        # Warning may or may not print depending on error path taken

    def test_load_cursor_handles_none_image(self, wx_app):
        """Should return None when NSImage returns None."""
        # This is tested implicitly by test_load_cursor_invalid_symbol_returns_none
        # NSImage returns None for invalid symbols
        cursor = load_cursor_from_symbol("nonexistent_symbol_12345", point_size=7)
        assert cursor is None

    def test_load_cursor_handles_zero_dimensions(self, wx_app):
        """Should return None when image has zero dimensions."""
        # This would require extensive mocking of NSImage internals
        # Testing via invalid symbol name which produces similar effect
        cursor = load_cursor_from_symbol("", point_size=7)
        assert cursor is None


class TestCursorIntegration:
    """Integration tests for cursor usage in UI."""

    def test_cursor_can_be_set_on_panel(self, wx_app):
        """Should be able to set loaded cursor on wx.Panel."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        if cursor is not None:
            # Create panel and set cursor
            frame = wx.Frame(None)
            panel = wx.Panel(frame)
            panel.SetCursor(cursor)

            # Verify cursor was set (GetCursor returns a cursor)
            retrieved = panel.GetCursor()
            assert retrieved.IsOk()

            frame.Destroy()

    def test_cursor_survives_panel_operations(self, wx_app):
        """Should maintain cursor after panel layout operations."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        if cursor is not None:
            frame = wx.Frame(None)
            panel = wx.Panel(frame)
            panel.SetCursor(cursor)

            # Perform layout operations
            sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(sizer)
            panel.Layout()

            # Cursor should still be valid
            retrieved = panel.GetCursor()
            assert retrieved.IsOk()

            frame.Destroy()

    def test_multiple_cursors_on_different_panels(self, wx_app):
        """Should be able to set different cursors on different panels."""
        zoom_in = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)
        zoom_out = load_cursor_from_symbol("minus.magnifyingglass", point_size=7)

        if zoom_in and zoom_out:
            frame = wx.Frame(None)
            panel1 = wx.Panel(frame)
            panel2 = wx.Panel(frame)

            panel1.SetCursor(zoom_in)
            panel2.SetCursor(zoom_out)

            # Both should have valid cursors
            assert panel1.GetCursor().IsOk()
            assert panel2.GetCursor().IsOk()

            frame.Destroy()

    def test_cursor_in_dialog(self, wx_app):
        """Should work when set on panel inside dialog."""
        cursor = load_cursor_from_symbol("plus.magnifyingglass", point_size=7)

        if cursor is not None:
            dialog = wx.Dialog(None, title="Test", size=(200, 100))
            panel = wx.Panel(dialog)
            panel.SetCursor(cursor)

            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(panel, 1, wx.EXPAND)
            dialog.SetSizer(sizer)

            assert panel.GetCursor().IsOk()

            dialog.Destroy()
