"""Tests for wxPython utility functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import wx
from PIL import Image

from app.gui import utils


class TestImageConversion:
    """Tests for PIL ↔ wx image conversion functions.

    These tests require wx.App to be initialized.
    """

    def test_pil_to_bitmap_rgb(self, wx_app):
        """Should convert RGB PIL Image to wx.Bitmap."""
        # Create a simple RGB PIL image
        pil_img = Image.new("RGB", (100, 50), color=(255, 0, 0))

        # Convert to wx.Bitmap
        bitmap = utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_bitmap_rgba(self, wx_app):
        """Should convert RGBA PIL Image to wx.Bitmap (converts to RGB)."""
        # Create an RGBA PIL image
        pil_img = Image.new("RGBA", (100, 50), color=(0, 255, 0, 128))

        # Convert to wx.Bitmap
        bitmap = utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_bitmap_grayscale(self, wx_app):
        """Should convert grayscale PIL Image to wx.Bitmap."""
        # Create a grayscale PIL image
        pil_img = Image.new("L", (100, 50), color=128)

        # Convert to wx.Bitmap
        bitmap = utils.pil_to_bitmap(pil_img)

        # Verify dimensions
        assert bitmap.GetWidth() == 100
        assert bitmap.GetHeight() == 50
        assert bitmap.IsOk()

    def test_pil_to_image_rgb(self, wx_app):
        """Should convert RGB PIL Image to wx.Image."""
        # Create a simple RGB PIL image
        pil_img = Image.new("RGB", (100, 50), color=(0, 0, 255))

        # Convert to wx.Image
        wx_img = utils.pil_to_image(pil_img)

        # Verify dimensions
        assert wx_img.GetWidth() == 100
        assert wx_img.GetHeight() == 50
        assert wx_img.IsOk()

    def test_pil_to_image_rgba(self, wx_app):
        """Should convert RGBA PIL Image to wx.Image (converts to RGB)."""
        # Create an RGBA PIL image
        pil_img = Image.new("RGBA", (100, 50), color=(255, 255, 0, 200))

        # Convert to wx.Image
        wx_img = utils.pil_to_image(pil_img)

        # Verify dimensions
        assert wx_img.GetWidth() == 100
        assert wx_img.GetHeight() == 50
        assert wx_img.IsOk()


class TestWidgetCreation:
    """Tests for widget creation helper functions.

    These tests require wx.App to be initialized.
    """

    def test_create_static_text_basic(self, wx_frame):
        """Should create a static text label."""
        label = utils.create_static_text(wx_frame, "Test Label")

        assert label.GetLabel() == "Test Label"
        assert isinstance(label, wx.StaticText)

    def test_create_static_text_with_font(self, wx_frame):
        """Should create a static text with custom font."""
        font = wx.Font(wx.FontInfo(16).Bold())
        label = utils.create_static_text(wx_frame, "Test", font=font)

        result_font = label.GetFont()
        assert result_font.GetPointSize() == 16
        assert result_font.GetWeight() == wx.FONTWEIGHT_BOLD

    def test_create_static_text_with_colour(self, wx_frame):
        """Should create a static text with custom colour."""
        red = wx.Colour(255, 0, 0)
        label = utils.create_static_text(wx_frame, "Test", colour=red)

        colour = label.GetForegroundColour()
        assert colour.Red() == 255
        assert colour.Green() == 0
        assert colour.Blue() == 0


class TestOpenFilesAndFolders:
    """Tests for open_files_and_folders() using mocked NSOpenPanel."""

    def test_returns_selected_paths(self):
        """Should return list of Paths when user selects files/folders."""
        mock_url1 = MagicMock()
        mock_url1.path.return_value = "/Users/test/Documents/card.pdf"
        mock_url2 = MagicMock()
        mock_url2.path.return_value = "/Users/test/Documents/Cards"

        mock_panel = MagicMock()
        mock_panel.runModal.return_value = 1
        mock_panel.URLs.return_value = [mock_url1, mock_url2]

        mock_cls = MagicMock()
        mock_cls.openPanel.return_value = mock_panel

        with patch.object(utils, "NSOpenPanel", mock_cls), patch.object(utils, "NSModalResponseOK", 1):
            result = utils.open_files_and_folders("Pick files", ["pdf"])

        assert result == [
            Path("/Users/test/Documents/card.pdf"),
            Path("/Users/test/Documents/Cards"),
        ]

    def test_returns_empty_on_cancel(self):
        """Should return empty list when user cancels the dialog."""
        mock_panel = MagicMock()
        mock_panel.runModal.return_value = 0

        mock_cls = MagicMock()
        mock_cls.openPanel.return_value = mock_panel

        with patch.object(utils, "NSOpenPanel", mock_cls), patch.object(utils, "NSModalResponseOK", 1):
            result = utils.open_files_and_folders("Pick files", ["pdf"])

        assert result == []

    def test_configures_panel_correctly(self):
        """Should configure NSOpenPanel with correct settings."""
        mock_panel = MagicMock()
        mock_panel.runModal.return_value = 0

        mock_cls = MagicMock()
        mock_cls.openPanel.return_value = mock_panel

        with patch.object(utils, "NSOpenPanel", mock_cls), patch.object(utils, "NSModalResponseOK", 1):
            utils.open_files_and_folders("Test Message", ["pdf"])

        mock_panel.setCanChooseFiles_.assert_called_once_with(True)
        mock_panel.setCanChooseDirectories_.assert_called_once_with(True)
        mock_panel.setAllowsMultipleSelection_.assert_called_once_with(True)
        mock_panel.setAllowedFileTypes_.assert_called_once_with(["pdf"])
        mock_panel.setMessage_.assert_called_once_with("Test Message")
