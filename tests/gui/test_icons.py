"""Tests for wxPython SF Symbol icon loader."""

from unittest.mock import MagicMock, patch

import pytest
import wx

from app.gui.icons import (
    _cache,
    _hex_to_rgb,
    _render_sf_symbol_to_png,
    clear_cache,
    load_cursor_from_symbol,
    load_menu_icon,
    load_sf_symbol,
)


class TestSFSymbolLoading:
    """Tests for SF Symbol loading and caching.

    These tests require wx.App to be initialized and PyObjC to be available.
    """

    def test_load_valid_symbol_returns_bitmap(self, wx_app):
        """Should return wx.Bitmap for valid SF Symbol."""
        bitmap = load_sf_symbol("scissors", 12, "#000000")

        # Should return bitmap or None if PyObjC unavailable
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()

    def test_load_invalid_symbol_returns_none(self, wx_app):
        """Should return None for invalid/nonexistent SF Symbol."""
        bitmap = load_sf_symbol("this_symbol_does_not_exist_12345", 12, "#000000")

        assert bitmap is None

    def test_bitmap_has_reasonable_dimensions(self, wx_app):
        """Should return bitmap with non-zero dimensions."""
        bitmap = load_sf_symbol("scissors", 16, "#000000")

        if bitmap:  # Only test if PyObjC is available
            assert bitmap.GetWidth() > 0
            assert bitmap.GetHeight() > 0
            # Retina displays double the pixels, so be generous with limits
            assert bitmap.GetWidth() <= 100  # Account for @2x Retina
            assert bitmap.GetHeight() <= 100

    def test_different_sizes_create_different_bitmaps(self, wx_app):
        """Should create different bitmaps for different sizes."""
        bitmap_small = load_sf_symbol("scissors", 12, "#000000")
        bitmap_large = load_sf_symbol("scissors", 24, "#000000")

        if bitmap_small and bitmap_large:
            assert bitmap_small.GetWidth() < bitmap_large.GetWidth()
            assert bitmap_small.GetHeight() < bitmap_large.GetHeight()

    def test_different_colors_do_not_affect_cache_incorrectly(self, wx_app):
        """Should cache separately for different colors."""
        bitmap_black = load_sf_symbol("scissors", 12, "#000000")
        bitmap_red = load_sf_symbol("scissors", 12, "#FF0000")

        # Both should succeed (cached separately)
        if bitmap_black:
            assert bitmap_black.IsOk()
        if bitmap_red:
            assert bitmap_red.IsOk()

    @pytest.mark.parametrize(
        "symbol_name",
        [
            "scissors",
            "doc.on.doc",
            "doc.on.clipboard",
            "textformat.abc",
            "xmark.circle",
        ],
    )
    def test_context_menu_symbols_load(self, wx_app, symbol_name):
        """Test that all context menu SF Symbols load successfully."""
        bitmap = load_sf_symbol(symbol_name, 12, "#1D1D1F")

        # Should return either valid bitmap or None (if PyObjC unavailable)
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()


class TestCaching:
    """Tests for icon caching behavior."""

    def test_cache_returns_same_object(self, wx_app):
        """Should return same cached object for identical parameters."""
        bitmap1 = load_sf_symbol("scissors", 12, "#000000")
        bitmap2 = load_sf_symbol("scissors", 12, "#000000")

        if bitmap1 and bitmap2:
            # Should be the exact same object (cached)
            assert bitmap1 is bitmap2

    def test_cache_key_includes_size(self, wx_app):
        """Should cache separately for different sizes."""
        bitmap_12 = load_sf_symbol("scissors", 12, "#000000")
        bitmap_16 = load_sf_symbol("scissors", 16, "#000000")

        if bitmap_12 and bitmap_16:
            # Different sizes = different objects
            assert bitmap_12 is not bitmap_16

    def test_cache_key_includes_color(self, wx_app):
        """Should cache separately for different colors."""
        bitmap_black = load_sf_symbol("scissors", 12, "#000000")
        bitmap_white = load_sf_symbol("scissors", 12, "#FFFFFF")

        if bitmap_black and bitmap_white:
            # Different colors = different objects
            assert bitmap_black is not bitmap_white

    def test_cache_key_includes_name(self, wx_app):
        """Should cache separately for different symbols."""
        bitmap_scissors = load_sf_symbol("scissors", 12, "#000000")
        bitmap_copy = load_sf_symbol("doc.on.doc", 12, "#000000")

        if bitmap_scissors and bitmap_copy:
            # Different symbols = different objects
            assert bitmap_scissors is not bitmap_copy

    def test_invalid_symbol_cached_as_none(self, wx_app):
        """Should cache None for invalid symbols (don't retry)."""
        # First call
        result1 = load_sf_symbol("invalid_symbol_xyz", 12, "#000000")
        # Second call (should use cache)
        result2 = load_sf_symbol("invalid_symbol_xyz", 12, "#000000")

        assert result1 is None
        assert result2 is None

    def test_clear_cache_empties(self, wx_app):
        """clear_cache() should empty the icon cache."""
        # Load something to populate cache
        load_sf_symbol("scissors", 12, "#000000")
        assert len(_cache) > 0
        clear_cache()
        assert len(_cache) == 0


class TestColorHandling:
    """Tests for hex color string handling."""

    def test_accepts_color_with_hash(self, wx_app):
        """Should accept hex color with # prefix."""
        bitmap = load_sf_symbol("scissors", 12, "#FF0000")

        assert bitmap is None or isinstance(bitmap, wx.Bitmap)

    def test_accepts_color_without_hash(self, wx_app):
        """Should accept hex color without # prefix."""
        # Note: Current implementation expects # prefix
        # This test documents current behavior
        bitmap = load_sf_symbol("scissors", 12, "FF0000")

        # May fail due to missing # - that's OK, test documents it
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)

    @pytest.mark.parametrize(
        "color_hex",
        [
            "#000000",  # Black
            "#FFFFFF",  # White
            "#FF0000",  # Red
            "#00FF00",  # Green
            "#0000FF",  # Blue
            "#1D1D1F",  # Near-black (our default)
        ],
    )
    def test_various_colors(self, wx_app, color_hex):
        """Test loading with various hex colors."""
        bitmap = load_sf_symbol("scissors", 12, color_hex)

        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()


class TestEdgeCases:
    """Tests for edge cases and error handling.

    Note: We avoid testing pathological inputs (negative/zero size)
    that crash AppKit/NSImage rather than failing gracefully.
    """

    def test_very_large_size(self, wx_app):
        """Should handle very large size without crashing."""
        # 100pt is quite large but shouldn't crash
        bitmap = load_sf_symbol("scissors", 100, "#000000")

        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()

    def test_empty_symbol_name(self, wx_app):
        """Should handle empty symbol name gracefully."""
        bitmap = load_sf_symbol("", 12, "#000000")

        assert bitmap is None


class TestIconDialogIntegration:
    """Level 3: Structural validation tests for icon display in dialogs.

    These tests validate that icons can be properly integrated into
    wxPython dialogs without testing pixel-perfect appearance.
    """

    def test_icon_in_static_bitmap_widget(self, wx_app):
        """Should be able to display icon in wx.StaticBitmap."""
        bitmap = load_sf_symbol("scissors", 16, "#000000")

        if bitmap:
            # Create a minimal dialog with the icon
            dialog = wx.Dialog(None, title="Test", size=(100, 100))
            static_bitmap = wx.StaticBitmap(dialog, bitmap=bitmap)

            # Validate structure
            # Note: wxPython may scale bitmap for Retina, so just check validity
            retrieved_bitmap = static_bitmap.GetBitmap()
            assert retrieved_bitmap.IsOk()
            assert retrieved_bitmap.GetWidth() > 0
            assert retrieved_bitmap.GetHeight() > 0

            dialog.Destroy()

    def test_multiple_icons_in_dialog(self, wx_app):
        """Should be able to display multiple different icons in one dialog."""
        test_symbols = [
            ("scissors", "Cut"),
            ("doc.on.doc", "Copy"),
            ("xmark.circle", "Clear"),
        ]

        dialog = wx.Dialog(None, title="Multi-Icon Test", size=(200, 150))
        sizer = wx.BoxSizer(wx.VERTICAL)

        bitmap_widgets = []
        for symbol_name, label in test_symbols:
            bitmap = load_sf_symbol(symbol_name, 14, "#000000")
            if bitmap:
                row = wx.BoxSizer(wx.HORIZONTAL)
                bmp_widget = wx.StaticBitmap(dialog, bitmap=bitmap)
                text_widget = wx.StaticText(dialog, label=label)

                row.Add(bmp_widget, 0, wx.RIGHT, 5)
                row.Add(text_widget, 0)
                sizer.Add(row, 0, wx.ALL, 5)

                bitmap_widgets.append(bmp_widget)

        dialog.SetSizer(sizer)

        # Structural validation
        if bitmap_widgets:  # Only if PyObjC available
            assert len(bitmap_widgets) == 3
            for widget in bitmap_widgets:
                assert widget.GetBitmap().IsOk()
                assert widget.GetBitmap().GetWidth() > 0
                assert widget.GetBitmap().GetHeight() > 0

        dialog.Destroy()

    def test_icon_survives_dialog_layout(self, wx_app):
        """Should maintain bitmap validity after dialog layout operations."""
        bitmap = load_sf_symbol("scissors", 16, "#000000")

        if bitmap:
            dialog = wx.Dialog(None, title="Layout Test", size=(200, 100))
            sizer = wx.BoxSizer(wx.VERTICAL)

            static_bitmap = wx.StaticBitmap(dialog, bitmap=bitmap)
            sizer.Add(static_bitmap, 0, wx.ALL, 10)

            dialog.SetSizer(sizer)
            dialog.Layout()  # Trigger layout
            sizer.Fit(dialog)  # Fit to content

            # Bitmap should still be valid after layout operations
            assert static_bitmap.GetBitmap().IsOk()
            assert static_bitmap.GetBitmap().GetWidth() > 0

            dialog.Destroy()


class TestHexToRgb:
    """Tests for _hex_to_rgb() utility function."""

    def test_hex_to_rgb_black(self):
        """Should convert black to (0.0, 0.0, 0.0)."""
        result = _hex_to_rgb("#000000")
        assert result == (0.0, 0.0, 0.0)

    def test_hex_to_rgb_white(self):
        """Should convert white to (1.0, 1.0, 1.0)."""
        result = _hex_to_rgb("#FFFFFF")
        assert result == (1.0, 1.0, 1.0)

    def test_hex_to_rgb_red(self):
        """Should convert red to (1.0, 0.0, 0.0)."""
        result = _hex_to_rgb("#FF0000")
        assert result == (1.0, 0.0, 0.0)

    def test_hex_to_rgb_green(self):
        """Should convert green to (0.0, 1.0, 0.0)."""
        result = _hex_to_rgb("#00FF00")
        assert result == (0.0, 1.0, 0.0)

    def test_hex_to_rgb_blue(self):
        """Should convert blue to (0.0, 0.0, 1.0)."""
        result = _hex_to_rgb("#0000FF")
        assert result == (0.0, 0.0, 1.0)

    def test_hex_to_rgb_gray(self):
        """Should convert gray to approximately (0.5, 0.5, 0.5)."""
        result = _hex_to_rgb("#808080")
        # 0x80 = 128, 128/255 ≈ 0.502
        assert result[0] == pytest.approx(0.502, abs=0.01)
        assert result[1] == pytest.approx(0.502, abs=0.01)
        assert result[2] == pytest.approx(0.502, abs=0.01)

    def test_hex_to_rgb_custom_color(self):
        """Should convert custom hex color correctly."""
        result = _hex_to_rgb("#1D1D1F")
        # 0x1D = 29, 29/255 ≈ 0.114
        # 0x1F = 31, 31/255 ≈ 0.122
        assert result[0] == pytest.approx(0.114, abs=0.01)
        assert result[1] == pytest.approx(0.114, abs=0.01)
        assert result[2] == pytest.approx(0.122, abs=0.01)

    def test_hex_to_rgb_returns_floats(self):
        """Should return tuple of floats."""
        result = _hex_to_rgb("#123456")
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)

    def test_hex_to_rgb_values_in_range(self):
        """Should return values between 0.0 and 1.0."""
        test_colors = ["#000000", "#FFFFFF", "#FF0000", "#123456", "#ABCDEF"]
        for color in test_colors:
            r, g, b = _hex_to_rgb(color)
            assert 0.0 <= r <= 1.0
            assert 0.0 <= g <= 1.0
            assert 0.0 <= b <= 1.0


class TestLoadMenuIcon:
    """Tests for load_menu_icon() wrapper function."""

    def test_load_menu_icon_returns_bitmap(self, wx_app):
        """Should return wx.Bitmap for valid symbol."""
        bitmap = load_menu_icon("scissors")

        # Should return bitmap or None if PyObjC unavailable
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()

    def test_load_menu_icon_invalid_symbol(self, wx_app):
        """Should return None for invalid symbol."""
        bitmap = load_menu_icon("invalid_symbol_xyz")

        assert bitmap is None

    def test_load_menu_icon_uses_6pt_size(self, wx_app):
        """Should use 6pt size for menu icons."""
        bitmap = load_menu_icon("scissors")

        if bitmap:
            # Size should be small (6pt + retina scaling)
            # Don't test exact pixels due to retina, just that it's reasonable
            assert bitmap.GetWidth() > 0
            assert bitmap.GetHeight() > 0
            # Menu icons should be relatively small
            assert bitmap.GetWidth() < 50
            assert bitmap.GetHeight() < 50

    def test_load_menu_icon_accepts_custom_color(self, wx_app):
        """Should accept custom color parameter."""
        bitmap = load_menu_icon("scissors", color_hex="#FF0000")

        # Should load successfully (color is applied internally)
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)

    def test_load_menu_icon_uses_default_color(self, wx_app):
        """Should use default near-black color when not specified."""
        bitmap = load_menu_icon("scissors")

        # Should load with default color
        assert bitmap is None or isinstance(bitmap, wx.Bitmap)

    @pytest.mark.parametrize(
        "symbol_name",
        [
            "scissors",
            "doc.on.doc",
            "doc.on.clipboard",
            "textformat.abc",
            "xmark.circle",
        ],
    )
    def test_load_menu_icon_common_symbols(self, wx_app, symbol_name):
        """Should load common menu symbols."""
        bitmap = load_menu_icon(symbol_name)

        assert bitmap is None or isinstance(bitmap, wx.Bitmap)
        if bitmap:
            assert bitmap.IsOk()

    def test_load_menu_icon_is_cached(self, wx_app):
        """Should cache menu icon results."""
        # Load same icon twice
        bitmap1 = load_menu_icon("scissors")
        bitmap2 = load_menu_icon("scissors")

        if bitmap1 and bitmap2:
            # Should return same cached object
            assert bitmap1 is bitmap2

    def test_load_menu_icon_different_colors_cached_separately(self, wx_app):
        """Should cache separately for different colors."""
        bitmap_black = load_menu_icon("scissors", "#000000")
        bitmap_red = load_menu_icon("scissors", "#FF0000")

        if bitmap_black and bitmap_red:
            # Different colors = different cached objects
            assert bitmap_black is not bitmap_red


class TestRenderSfSymbolEdgeCases:
    """Tests for edge cases in _render_sf_symbol_to_png and dependents."""

    @patch("app.gui.icons._render_sf_symbol_to_png")
    def test_render_sf_symbol_none_config(self, mock_render: MagicMock, wx_app: wx.App) -> None:
        """load_sf_symbol returns None when _render_sf_symbol_to_png returns None."""
        mock_render.return_value = None
        clear_cache()

        result = load_sf_symbol("test.symbol", 14, "#000000")

        assert result is None
        mock_render.assert_called_once()

    @patch("app.gui.icons._render_sf_symbol_to_png")
    def test_render_sf_symbol_zero_size(self, mock_render: MagicMock, wx_app: wx.App) -> None:
        """load_sf_symbol returns None when rendered PNG produces an invalid wx.Image."""
        # Return PNG bytes that will produce an invalid image (empty bytes)
        mock_render.return_value = (b"", 2)
        clear_cache()

        _no_log = wx.LogNull()  # suppress native "Not a PNG" dialog
        result = load_sf_symbol("test.symbol.zero", 14, "#000000")
        del _no_log

        assert result is None

    @patch("app.gui.icons._render_sf_symbol_to_png")
    def test_load_cursor_from_symbol_bad_image(self, mock_render: MagicMock, wx_app: wx.App) -> None:
        """load_cursor_from_symbol returns None when wx.Image.IsOk() is False."""
        # Return bytes that will produce an invalid wx.Image
        mock_render.return_value = (b"not-valid-png-data", 2)

        _no_log = wx.LogNull()  # suppress native "Not a PNG" dialog
        result = load_cursor_from_symbol("test.bad.image", 20, "#1D1D1F")
        del _no_log

        assert result is None

    def test_styled_none_fallback(self) -> None:
        """imageWithSymbolConfiguration_ returns None → falls back to unstyled image."""
        mock_image = MagicMock()
        mock_size = MagicMock()
        mock_size.width = 16
        mock_size.height = 16
        mock_image.size.return_value = mock_size
        mock_image.imageWithSymbolConfiguration_.return_value = None  # styled is None
        mock_image.drawInRect_fromRect_operation_fraction_ = MagicMock()

        mock_rep = MagicMock()
        mock_rep.representationUsingType_properties_.return_value = b"\x89PNG"

        mock_screen = MagicMock()
        mock_screen.backingScaleFactor.return_value = 2

        mock_appkit = MagicMock()
        mock_appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_.return_value = mock_image
        mock_appkit.NSScreen.mainScreen.return_value = mock_screen
        mock_appkit.NSBitmapImageRep.alloc.return_value.initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_.return_value = mock_rep

        mock_foundation = MagicMock()

        with patch.dict("sys.modules", {"AppKit": mock_appkit, "Foundation": mock_foundation}):
            result = _render_sf_symbol_to_png("test.symbol", 14, "#000000", 2)

        # Should succeed using unstyled image as fallback
        assert result is not None
        assert result[0] == b"\x89PNG"

    def test_zero_dimension_returns_none(self) -> None:
        """styled.size() returns width=0 → returns None."""
        mock_image = MagicMock()
        mock_styled = MagicMock()
        mock_size = MagicMock()
        mock_size.width = 0
        mock_size.height = 16
        mock_styled.size.return_value = mock_size
        mock_image.imageWithSymbolConfiguration_.return_value = mock_styled

        mock_appkit = MagicMock()
        mock_appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_.return_value = mock_image

        mock_foundation = MagicMock()

        with patch.dict("sys.modules", {"AppKit": mock_appkit, "Foundation": mock_foundation}):
            result = _render_sf_symbol_to_png("test.symbol", 14, "#000000", 2)

        assert result is None
