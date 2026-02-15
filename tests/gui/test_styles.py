"""Tests for app.gui.styles module."""
import wx
import pytest

from app.gui.styles import Color, Font, Layout


class TestColor:
    """Tests for Color class."""

    def test_from_hex_with_hash(self, wx_app):
        c = Color.from_hex("#FF0000")
        assert c.Red() == 255
        assert c.Green() == 0
        assert c.Blue() == 0

    def test_from_hex_without_hash(self, wx_app):
        c = Color.from_hex("00FF00")
        assert c.Red() == 0
        assert c.Green() == 255
        assert c.Blue() == 0

    def test_from_hex_mixed_case(self, wx_app):
        c = Color.from_hex("#aaBBcc")
        assert c.Red() == 0xAA
        assert c.Green() == 0xBB
        assert c.Blue() == 0xCC

    def test_semantic_colors_exist(self, wx_app):
        """All semantic color constants are wx.Colour instances."""
        colors = [
            Color.BG_PRIMARY, Color.BG_SECONDARY, Color.BG_SELECTED,
            Color.TEXT_PRIMARY, Color.TEXT_SECONDARY,
            Color.ACCENT, Color.SUCCESS, Color.WARNING, Color.ERROR,
            Color.MANUAL_BLUE,
        ]
        for c in colors:
            assert isinstance(c, wx.Colour)

    def test_accent_is_blue(self, wx_app):
        assert Color.ACCENT.Red() == 0
        assert Color.ACCENT.Blue() == 255


class TestFont:
    """Tests for Font class."""

    def test_title_font(self, wx_app):
        f = Font.TITLE()
        assert isinstance(f, wx.Font)
        assert f.GetPointSize() == 16
        assert f.GetWeight() == wx.FONTWEIGHT_BOLD

    def test_body_font(self, wx_app):
        f = Font.BODY()
        assert isinstance(f, wx.Font)
        assert f.GetPointSize() == 12

    def test_mono_font(self, wx_app):
        f = Font.MONO()
        assert isinstance(f, wx.Font)
        assert f.GetPointSize() == 11
        assert f.GetFamily() == wx.FONTFAMILY_TELETYPE

    def test_heading_font(self, wx_app):
        f = Font.HEADING()
        assert f.GetPointSize() == 13
        assert f.GetWeight() == wx.FONTWEIGHT_BOLD

    def test_small_font(self, wx_app):
        f = Font.SMALL()
        assert f.GetPointSize() == 11

    def test_from_tuple_basic(self, wx_app):
        f = Font.from_tuple(("Helvetica Neue", 14))
        assert isinstance(f, wx.Font)
        assert f.GetPointSize() == 14

    def test_from_tuple_bold(self, wx_app):
        f = Font.from_tuple(("Helvetica Neue", 14, "bold"))
        assert f.GetWeight() == wx.FONTWEIGHT_BOLD

    def test_from_tuple_mono(self, wx_app):
        f = Font.from_tuple(("Menlo", 12))
        assert f.GetFamily() == wx.FONTFAMILY_TELETYPE


class TestLayout:
    """Tests for Layout class."""

    def test_window_dimensions(self, wx_app):
        assert Layout.WINDOW_WIDTH == 1200
        assert Layout.WINDOW_HEIGHT == 750

    def test_preview_width(self, wx_app):
        assert Layout.PREVIEW_WIDTH == 450

    def test_pad(self, wx_app):
        assert Layout.PAD == 10

    def test_row_height(self, wx_app):
        assert Layout.ROW_HEIGHT == 36
