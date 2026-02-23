"""Tests for app.core.ocr_engine module."""
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

import app.core.ocr_engine as ocr_module
from app.core.ocr_engine import (
    preprocess_image, extract_text, extract_text_all_pages,
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

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_calls_tesserocr(self, mock_api_cls):
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = "Hello World"
        mock_api_cls.return_value = mock_api
        img = _make_test_image()
        result = extract_text(img)
        assert result == "Hello World"
        mock_api.SetImage.assert_called_once()
        mock_api.GetUTF8Text.assert_called_once()

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_sets_psm_auto(self, mock_api_cls):
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = ""
        mock_api_cls.return_value = mock_api
        img = _make_test_image()
        extract_text(img)
        mock_api.SetPageSegMode.assert_called_once()

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_sets_dict_penalty(self, mock_api_cls):
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = ""
        mock_api_cls.return_value = mock_api
        img = _make_test_image()
        extract_text(img)
        mock_api.SetVariable.assert_called_once_with(
            "language_model_penalty_non_dict_word", "0.15"
        )

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_strips_result(self, mock_api_cls):
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = "  text with spaces  \n"
        mock_api_cls.return_value = mock_api
        result = extract_text(_make_test_image())
        assert result == "text with spaces"


class TestExtractTextAllPages:
    """Tests for extract_text_all_pages()."""

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_combines_pages(self, mock_api_cls):
        texts = iter(["Page 1 text", "Page 2 text"])
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.side_effect = lambda: next(texts)
        mock_api_cls.return_value = mock_api
        images = [_make_test_image(), _make_test_image()]
        result = extract_text_all_pages(images)
        assert "Page 1 text" in result
        assert "Page 2 text" in result
        assert "\n\n" in result

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_empty_list(self, mock_api_cls):
        result = extract_text_all_pages([])
        assert result == ""
        mock_api_cls.assert_not_called()

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_skips_empty_pages(self, mock_api_cls):
        texts = iter(["Page 1", "", "Page 3"])
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.side_effect = lambda: next(texts)
        mock_api_cls.return_value = mock_api
        images = [_make_test_image(), _make_test_image(), _make_test_image()]
        result = extract_text_all_pages(images)
        assert result == "Page 1\n\nPage 3"


class TestTessdataPath:
    """Tests for tessdata path resolution."""

    def test_dev_path_points_to_runtime_content(self):
        """In dev mode, tessdata path is under project root/_runtime_content/tessdata."""
        import importlib
        import sys

        # In dev mode sys._MEIPASS does not exist — just reload
        if hasattr(sys, '_MEIPASS'):
            delattr(sys, '_MEIPASS')
        importlib.reload(ocr_module)
        path = ocr_module._tessdata_path
        assert path.endswith("_runtime_content/tessdata/fast")
        assert "_MEIPASS" not in path

    def test_bundled_path_uses_meipass(self):
        """In bundled app, tessdata path is under sys._MEIPASS/_runtime_content/tessdata."""
        import importlib
        import sys

        sys._MEIPASS = "/tmp/fake_meipass"  # type: ignore[attr-defined]
        try:
            importlib.reload(ocr_module)
            assert ocr_module._tessdata_path == "/tmp/fake_meipass/_runtime_content/tessdata/fast"
        finally:
            del sys._MEIPASS  # type: ignore[attr-defined]
            importlib.reload(ocr_module)


class TestPreprocessImageModes:
    """Tests for preprocess_image() with different input modes."""

    def test_rgba_input(self):
        """RGBA image is converted to grayscale."""
        img = Image.new("RGBA", (100, 50), (255, 0, 0, 128))
        result = preprocess_image(img)
        assert result.mode == "L"
        assert result.size == (100, 50)

    def test_palette_input(self):
        """Palette (P) mode image is converted to grayscale."""
        img = Image.new("P", (100, 50))
        result = preprocess_image(img)
        assert result.mode == "L"
        assert result.size == (100, 50)

    def test_one_bit_input(self):
        """1-bit (binary) image is converted to grayscale."""
        img = Image.new("1", (100, 50))
        result = preprocess_image(img)
        assert result.mode == "L"
        assert result.size == (100, 50)


class TestExtractTextErrors:
    """Tests for extract_text() error handling."""

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI", side_effect=RuntimeError("init failed"))
    def test_tesseract_init_failure(self, mock_api_cls):
        """Tesseract initialization failure raises RuntimeError."""
        with pytest.raises(RuntimeError, match="init failed"):
            extract_text(_make_test_image())

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_get_utf8_text_exception(self, mock_api_cls):
        """GetUTF8Text exception propagates."""
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.side_effect = RuntimeError("extraction failed")
        mock_api_cls.return_value = mock_api

        with pytest.raises(RuntimeError, match="extraction failed"):
            extract_text(_make_test_image())


class TestExtractTextAllPagesEdgeCases:
    """Edge case tests for extract_text_all_pages()."""

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_single_page_no_separator(self, mock_api_cls):
        """Single page result has no separator."""
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = "Single page text"
        mock_api_cls.return_value = mock_api

        result = extract_text_all_pages([_make_test_image()])
        assert result == "Single page text"
        assert "\n\n" not in result

    @patch("app.core.ocr_engine.tesserocr.PyTessBaseAPI")
    def test_all_pages_empty(self, mock_api_cls):
        """All pages returning empty text gives empty result."""
        mock_api = MagicMock()
        mock_api.__enter__ = MagicMock(return_value=mock_api)
        mock_api.__exit__ = MagicMock(return_value=False)
        mock_api.GetUTF8Text.return_value = "   "  # whitespace-only, strips to empty
        mock_api_cls.return_value = mock_api

        result = extract_text_all_pages([_make_test_image(), _make_test_image()])
        assert result == ""
