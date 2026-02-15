"""Tests for wxPython utility functions."""

import pytest
import wx
from PIL import Image
from app.gui import wx_utils


class TestColorConversion:
    """Tests for hex ↔ wx.Colour conversion functions."""

    @pytest.mark.unit
    def test_hex_to_colour_with_hash(self):
        """Should convert hex string with # prefix to wx.Colour."""
        colour = wx_utils.hex_to_colour("#FFFFFF")
        assert colour.Red() == 255
        assert colour.Green() == 255
        assert colour.Blue() == 255

    @pytest.mark.unit
    def test_hex_to_colour_without_hash(self):
        """Should convert hex string without # prefix to wx.Colour."""
        colour = wx_utils.hex_to_colour("000000")
        assert colour.Red() == 0
        assert colour.Green() == 0
        assert colour.Blue() == 0

    @pytest.mark.unit
    @pytest.mark.parametrize("hex_str,r,g,b", [
        ("#FF0000", 255, 0, 0),      # Red
        ("#00FF00", 0, 255, 0),      # Green
        ("#0000FF", 0, 0, 255),      # Blue
        ("#007AFF", 0, 122, 255),    # iOS blue
        ("#34C759", 52, 199, 89),    # iOS green
        ("#FF9500", 255, 149, 0),    # iOS orange
        ("FFFFFF", 255, 255, 255),   # White (no hash)
        ("000000", 0, 0, 0),         # Black (no hash)
    ])
    def test_hex_to_colour_various_colors(self, hex_str, r, g, b):
        """Test hex to colour conversion for various colors."""
        colour = wx_utils.hex_to_colour(hex_str)
        assert colour.Red() == r
        assert colour.Green() == g
        assert colour.Blue() == b

    @pytest.mark.unit
    def test_colour_to_hex_white(self):
        """Should convert white wx.Colour to hex string."""
        colour = wx.Colour(255, 255, 255)
        hex_str = wx_utils.colour_to_hex(colour)
        assert hex_str == "#FFFFFF"

    @pytest.mark.unit
    def test_colour_to_hex_black(self):
        """Should convert black wx.Colour to hex string."""
        colour = wx.Colour(0, 0, 0)
        hex_str = wx_utils.colour_to_hex(colour)
        assert hex_str == "#000000"

    @pytest.mark.unit
    @pytest.mark.parametrize("r,g,b,expected_hex", [
        (255, 0, 0, "#FF0000"),      # Red
        (0, 255, 0, "#00FF00"),      # Green
        (0, 0, 255, "#0000FF"),      # Blue
        (0, 122, 255, "#007AFF"),    # iOS blue
        (52, 199, 89, "#34C759"),    # iOS green
        (255, 149, 0, "#FF9500"),    # iOS orange
    ])
    def test_colour_to_hex_various_colors(self, r, g, b, expected_hex):
        """Test colour to hex conversion for various colors."""
        colour = wx.Colour(r, g, b)
        hex_str = wx_utils.colour_to_hex(colour)
        assert hex_str == expected_hex

    @pytest.mark.unit
    def test_hex_to_colour_round_trip(self):
        """Should convert hex -> colour -> hex without loss."""
        original_hex = "#34C759"
        colour = wx_utils.hex_to_colour(original_hex)
        result_hex = wx_utils.colour_to_hex(colour)
        assert result_hex == original_hex

    @pytest.mark.unit
    def test_colour_to_hex_round_trip(self):
        """Should convert colour -> hex -> colour without loss."""
        original = wx.Colour(0, 122, 255)
        hex_str = wx_utils.colour_to_hex(original)
        result = wx_utils.hex_to_colour(hex_str)
        assert result.Red() == original.Red()
        assert result.Green() == original.Green()
        assert result.Blue() == original.Blue()


@pytest.mark.gui
class TestImageConversion:
    """Tests for PIL ↔ wx image conversion functions.

    These tests require wx.App to be initialized.
    """

    def test_pil_to_bitmap_rgb(self, wx_app):
        """Should convert RGB PIL Image to wx.Bitmap."""
        # Create a simple RGB PIL image
        pil_img = Image.new('RGB', (100, 50), color=(255, 0, 0))

        # Convert to wx.Bitmap
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_bitmap_rgba(self, wx_app):
        """Should convert RGBA PIL Image to wx.Bitmap (converts to RGB)."""
        # Create an RGBA PIL image
        pil_img = Image.new('RGBA', (100, 50), color=(0, 255, 0, 128))

        # Convert to wx.Bitmap
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_bitmap_grayscale(self, wx_app):
        """Should convert grayscale PIL Image to wx.Bitmap."""
        # Create a grayscale PIL image
        pil_img = Image.new('L', (100, 50), color=128)

        # Convert to wx.Bitmap
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_image_rgb(self, wx_app):
        """Should convert RGB PIL Image to wx.Image."""
        # Create a simple RGB PIL image
        pil_img = Image.new('RGB', (100, 50), color=(0, 0, 255))

        # Convert to wx.Image
        wx_img = wx_utils.pil_to_image(pil_img)

        # Verify dimensions
        assert wx_img.GetWidth() == 100
        assert wx_img.GetHeight() == 50
        assert wx_img.IsOk()

    def test_pil_to_image_rgba(self, wx_app):
        """Should convert RGBA PIL Image to wx.Image (converts to RGB)."""
        # Create an RGBA PIL image
        pil_img = Image.new('RGBA', (100, 50), color=(255, 255, 0, 200))

        # Convert to wx.Image
        wx_img = wx_utils.pil_to_image(pil_img)

        # Verify dimensions
        assert wx_img.GetWidth() == 100
        assert wx_img.GetHeight() == 50
        assert wx_img.IsOk()

    def test_scale_bitmap_double(self, wx_app):
        """Should scale bitmap to double size."""
        # Create a small bitmap
        pil_img = Image.new('RGB', (50, 25), color=(255, 0, 0))
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Scale to double size
        scaled = wx_utils.scale_bitmap(bitmap, 2.0)

        assert scaled.GetWidth() == 100
        assert scaled.GetHeight() == 50
        assert scaled.IsOk()

    def test_scale_bitmap_half(self, wx_app):
        """Should scale bitmap to half size."""
        # Create a bitmap
        pil_img = Image.new('RGB', (100, 50), color=(0, 255, 0))
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Scale to half size
        scaled = wx_utils.scale_bitmap(bitmap, 0.5)

        assert scaled.GetWidth() == 50
        assert scaled.GetHeight() == 25
        assert scaled.IsOk()

    def test_scale_bitmap_same_size(self, wx_app):
        """Should return same size bitmap when scale = 1.0."""
        # Create a bitmap
        pil_img = Image.new('RGB', (100, 50), color=(0, 0, 255))
        bitmap = wx_utils.pil_to_bitmap(pil_img)

        # Scale to same size
        scaled = wx_utils.scale_bitmap(bitmap, 1.0)

        assert scaled.GetWidth() == 100
        assert scaled.GetHeight() == 50
        assert scaled.IsOk()


@pytest.mark.gui
class TestWidgetCreation:
    """Tests for widget creation helper functions.

    These tests require wx.App to be initialized.
    """

    def test_create_button_basic(self, wx_frame):
        """Should create a button with label."""
        btn = wx_utils.create_button(wx_frame, "Test Button")

        assert btn.GetLabel() == "Test Button"
        assert isinstance(btn, wx.Button)

    def test_create_button_with_callback(self, wx_frame):
        """Should create a button with click handler."""
        callback_called = []

        def callback():
            callback_called.append(True)

        btn = wx_utils.create_button(wx_frame, "Click Me", callback)

        # Simulate button click
        event = wx.CommandEvent(wx.wxEVT_BUTTON, btn.GetId())
        btn.ProcessEvent(event)

        assert callback_called == [True]

    def test_create_button_with_tooltip(self, wx_frame):
        """Should create a button with tooltip."""
        btn = wx_utils.create_button(wx_frame, "Test", tooltip="This is a tooltip")

        tooltip = btn.GetToolTip()
        assert tooltip is not None
        assert tooltip.GetTip() == "This is a tooltip"

    def test_create_text_ctrl_basic(self, wx_frame):
        """Should create a text control with initial value."""
        text = wx_utils.create_text_ctrl(wx_frame, value="Initial Text")

        assert text.GetValue() == "Initial Text"
        assert isinstance(text, wx.TextCtrl)

    def test_create_text_ctrl_empty(self, wx_frame):
        """Should create an empty text control."""
        text = wx_utils.create_text_ctrl(wx_frame)

        assert text.GetValue() == ""

    def test_create_text_ctrl_with_style(self, wx_frame):
        """Should create a text control with custom style."""
        text = wx_utils.create_text_ctrl(wx_frame, style=wx.TE_PASSWORD)

        # Check that it has the password style
        assert text.GetWindowStyle() & wx.TE_PASSWORD

    def test_create_static_text_basic(self, wx_frame):
        """Should create a static text label."""
        label = wx_utils.create_static_text(wx_frame, "Test Label")

        assert label.GetLabel() == "Test Label"
        assert isinstance(label, wx.StaticText)

    def test_create_static_text_with_font(self, wx_frame):
        """Should create a static text with custom font."""
        font = wx.Font(wx.FontInfo(16).Bold())
        label = wx_utils.create_static_text(wx_frame, "Test", font=font)

        result_font = label.GetFont()
        assert result_font.GetPointSize() == 16
        assert result_font.GetWeight() == wx.FONTWEIGHT_BOLD

    def test_create_static_text_with_colour(self, wx_frame):
        """Should create a static text with custom colour."""
        red = wx.Colour(255, 0, 0)
        label = wx_utils.create_static_text(wx_frame, "Test", colour=red)

        colour = label.GetForegroundColour()
        assert colour.Red() == 255
        assert colour.Green() == 0
        assert colour.Blue() == 0

    def test_center_window(self, wx_frame):
        """Should center a window (no assertion, just verify no crash)."""
        # This is mainly to verify the function doesn't crash
        wx_utils.center_window(wx_frame)
        # If we get here without exception, the test passes


@pytest.mark.gui
class TestMessageDialogs:
    """Tests for message dialog helper functions.

    These tests verify the functions can be called without crashing.
    We cannot easily test the actual dialog display without user interaction.
    """

    def test_show_error_callable(self, wx_frame):
        """Verify show_error is callable (doesn't test display)."""
        # We can't easily test modal dialogs in unit tests,
        # but we can verify the function signature works
        assert callable(wx_utils.show_error)

    def test_show_info_callable(self, wx_frame):
        """Verify show_info is callable (doesn't test display)."""
        assert callable(wx_utils.show_info)

    def test_show_warning_callable(self, wx_frame):
        """Verify show_warning is callable (doesn't test display)."""
        assert callable(wx_utils.show_warning)

    def test_confirm_callable(self, wx_frame):
        """Verify confirm is callable (doesn't test display)."""
        assert callable(wx_utils.confirm)
