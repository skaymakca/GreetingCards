"""Tests for app.core.ocr_engine module."""
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

import app.core.ocr_engine as ocr_module
from app.core.ocr_engine import (
    preprocess_image, extract_text, extract_text_all_pages, is_tesseract_available,
)


def _make_test_image(width=100, height=50, color="white"):
    """Create a small test image."""
    return Image.new("RGB", (width, height), color)


class TestPreprocessImage:
    """Tests for preprocess_image()."""

    def test_returns_grayscale(self):
        img = _make_test_image()
        result = preprocess_image(img)
        assert result.mode == "L"

    def test_preserves_dimensions(self):
        img = _make_test_image(200, 100)
        result = preprocess_image(img)
        assert result.size == (200, 100)

    def test_original_unchanged(self):
        img = _make_test_image()
        original_mode = img.mode
        preprocess_image(img)
        assert img.mode == original_mode

    def test_handles_grayscale_input(self):
        img = Image.new("L", (100, 50), 128)
        result = preprocess_image(img)
        assert result.mode == "L"


class TestExtractText:
    """Tests for extract_text()."""

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_calls_pytesseract(self, mock_ocr):
        mock_ocr.return_value = "Hello World"
        img = _make_test_image()
        result = extract_text(img)
        assert result == "Hello World"
        mock_ocr.assert_called_once()

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_passes_psm6_config(self, mock_ocr):
        mock_ocr.return_value = ""
        img = _make_test_image()
        extract_text(img)
        _, kwargs = mock_ocr.call_args
        assert "--psm 6" in kwargs.get("config", "")

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_strips_result(self, mock_ocr):
        mock_ocr.return_value = "  text with spaces  \n"
        result = extract_text(_make_test_image())
        assert result == "text with spaces"


class TestExtractTextAllPages:
    """Tests for extract_text_all_pages()."""

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_combines_pages(self, mock_ocr):
        mock_ocr.side_effect = ["Page 1 text", "Page 2 text"]
        images = [_make_test_image(), _make_test_image()]
        result = extract_text_all_pages(images)
        assert "Page 1 text" in result
        assert "Page 2 text" in result
        assert "\n\n" in result

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_empty_list(self, mock_ocr):
        result = extract_text_all_pages([])
        assert result == ""
        mock_ocr.assert_not_called()

    @patch("app.core.ocr_engine.pytesseract.image_to_string")
    def test_skips_empty_pages(self, mock_ocr):
        mock_ocr.side_effect = ["Page 1", "", "Page 3"]
        images = [_make_test_image(), _make_test_image(), _make_test_image()]
        result = extract_text_all_pages(images)
        assert result == "Page 1\n\nPage 3"


class TestBundledTesseractPathResolution:
    """Tests for bundled app Tesseract path resolution (lines 10-19)."""

    def test_bundled_finds_homebrew_arm(self):
        """When bundled and no tesseract in PATH, finds Apple Silicon Homebrew path."""
        import importlib
        import app.core.ocr_engine as ocr_mod

        with patch("app.core.paths.is_bundled", return_value=True), \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile") as mock_isfile, \
             patch("os.access") as mock_access:
            mock_isfile.side_effect = lambda p: p == "/opt/homebrew/bin/tesseract"
            mock_access.side_effect = lambda p, _: p == "/opt/homebrew/bin/tesseract"
            importlib.reload(ocr_mod)

            assert ocr_mod.pytesseract.pytesseract.tesseract_cmd == "/opt/homebrew/bin/tesseract"

        # Restore module to clean state
        importlib.reload(ocr_mod)

    def test_bundled_finds_intel_homebrew(self):
        """When ARM path doesn't exist, falls back to Intel Homebrew path."""
        import importlib
        import app.core.ocr_engine as ocr_mod

        with patch("app.core.paths.is_bundled", return_value=True), \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile") as mock_isfile, \
             patch("os.access") as mock_access:
            mock_isfile.side_effect = lambda p: p == "/usr/local/bin/tesseract"
            mock_access.side_effect = lambda p, _: p == "/usr/local/bin/tesseract"
            importlib.reload(ocr_mod)

            assert ocr_mod.pytesseract.pytesseract.tesseract_cmd == "/usr/local/bin/tesseract"

        importlib.reload(ocr_mod)

    def test_not_bundled_skips_path_search(self):
        """When not bundled, does not search for tesseract binary."""
        import importlib
        import app.core.ocr_engine as ocr_mod

        with patch("app.core.paths.is_bundled", return_value=False), \
             patch("os.path.isfile") as mock_isfile:
            importlib.reload(ocr_mod)
            mock_isfile.assert_not_called()

        importlib.reload(ocr_mod)


class TestTesseractAvailability:
    """Tests for is_tesseract_available() and graceful degradation."""

    def setup_method(self):
        ocr_module._tesseract_available = None

    def teardown_method(self):
        ocr_module._tesseract_available = None

    @patch("app.core.ocr_engine.shutil.which", return_value="/opt/homebrew/bin/tesseract")
    def test_available_when_in_path(self, mock_which):
        assert is_tesseract_available() is True
        assert ocr_module._tesseract_available is True

    @patch("app.core.ocr_engine.pytesseract.get_tesseract_version",
           side_effect=ocr_module.pytesseract.TesseractNotFoundError)
    @patch("app.core.ocr_engine.shutil.which", return_value=None)
    def test_unavailable_when_not_found(self, mock_which, mock_version):
        assert is_tesseract_available() is False
        assert ocr_module._tesseract_available is False

    @patch("app.core.ocr_engine.shutil.which", return_value="/usr/bin/tesseract")
    def test_caches_result(self, mock_which):
        assert is_tesseract_available() is True
        mock_which.reset_mock()
        # Second call should use cache
        assert is_tesseract_available() is True
        mock_which.assert_not_called()

    def test_extract_text_returns_empty_when_unavailable(self):
        ocr_module._tesseract_available = False
        img = _make_test_image()
        assert extract_text(img) == ""

    def test_extract_text_all_pages_returns_empty_when_unavailable(self):
        ocr_module._tesseract_available = False
        images = [_make_test_image(), _make_test_image()]
        assert extract_text_all_pages(images) == ""
