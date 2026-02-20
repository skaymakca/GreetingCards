"""Tests for app.core.pdf_renderer module."""
import io
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from app.core.pdf_renderer import _capped_zoom, autocrop_whitespace, render_pdf_page, render_all_pages, get_page_count


class TestCappedZoom:
    """Tests for _capped_zoom()."""

    def test_no_images_uses_target_dpi(self):
        """Page with no embedded images uses the requested DPI directly."""
        page = MagicMock()
        page.get_image_info.return_value = []
        matrix = _capped_zoom(page, 200)
        expected_zoom = 200 / 72
        assert abs(matrix.a - expected_zoom) < 0.01
        assert abs(matrix.d - expected_zoom) < 0.01

    def test_high_native_dpi_caps_zoom(self):
        """When native image DPI < requested DPI, zoom is capped to native."""
        page = MagicMock()
        page.get_image_info.return_value = [{"xres": 150, "yres": 150}]
        matrix = _capped_zoom(page, 300)
        # Should cap at 150/72 instead of 300/72
        expected_zoom = 150 / 72
        assert abs(matrix.a - expected_zoom) < 0.01

    def test_low_native_dpi_not_exceeded(self):
        """When native DPI is lower than target, zoom is capped to native."""
        page = MagicMock()
        page.get_image_info.return_value = [{"xres": 100, "yres": 100}]
        matrix = _capped_zoom(page, 200)
        expected_zoom = 100 / 72
        assert abs(matrix.a - expected_zoom) < 0.01

    def test_native_dpi_higher_than_target(self):
        """When native DPI exceeds target, uses target DPI."""
        page = MagicMock()
        page.get_image_info.return_value = [{"xres": 600, "yres": 600}]
        matrix = _capped_zoom(page, 200)
        expected_zoom = 200 / 72
        assert abs(matrix.a - expected_zoom) < 0.01

    def test_multiple_images_uses_max(self):
        """Multiple images — uses the highest native DPI."""
        page = MagicMock()
        page.get_image_info.return_value = [
            {"xres": 100, "yres": 100},
            {"xres": 300, "yres": 300},
        ]
        matrix = _capped_zoom(page, 400)
        # Should cap at 300/72
        expected_zoom = 300 / 72
        assert abs(matrix.a - expected_zoom) < 0.01


class TestAutocropWhitespace:
    """Tests for autocrop_whitespace()."""

    def test_crops_white_border(self):
        """White border around content is removed."""
        # Create image with white border and dark center
        img = Image.new("RGB", (200, 200), "white")
        for x in range(50, 150):
            for y in range(50, 150):
                img.putpixel((x, y), (0, 0, 0))
        result = autocrop_whitespace(img, padding=0)
        # Should be significantly smaller than original
        assert result.width < 200
        assert result.height < 200

    def test_padding_added(self):
        """Padding is added around the cropped content."""
        img = Image.new("RGB", (200, 200), "white")
        for x in range(80, 120):
            for y in range(80, 120):
                img.putpixel((x, y), (0, 0, 0))
        no_pad = autocrop_whitespace(img, padding=0)
        with_pad = autocrop_whitespace(img, padding=20)
        assert with_pad.width > no_pad.width
        assert with_pad.height > no_pad.height

    def test_all_white_returns_original(self):
        """All-white image returns the original (no bbox found)."""
        img = Image.new("RGB", (100, 100), "white")
        result = autocrop_whitespace(img)
        assert result.size == img.size

    def test_preserves_content(self):
        """Cropped image still contains the dark content."""
        img = Image.new("RGB", (200, 200), "white")
        for x in range(90, 110):
            for y in range(90, 110):
                img.putpixel((x, y), (10, 10, 10))
        result = autocrop_whitespace(img, padding=5)
        # The result should not be all white
        pixels = list(result.get_flattened_data())
        has_dark = any(p[0] < 50 for p in pixels)
        assert has_dark

    def test_near_white_threshold(self):
        """Pixels near the threshold are considered background."""
        img = Image.new("RGB", (100, 100), (250, 250, 250))
        # Add a dark spot
        for x in range(40, 60):
            for y in range(40, 60):
                img.putpixel((x, y), (0, 0, 0))
        result = autocrop_whitespace(img, threshold=245)
        assert result.width < 100


def _make_mock_doc(num_pages=1):
    """Create a mock fitz document with pages."""
    doc = MagicMock()
    pages = []
    for i in range(num_pages):
        page = MagicMock()
        page.get_image_info.return_value = []
        pix = MagicMock()
        # Create a small real PNG for tobytes
        buf = io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(buf, format="PNG")
        pix.tobytes.return_value = buf.getvalue()
        page.get_pixmap.return_value = pix
        pages.append(page)

    doc.__getitem__ = lambda self, idx: pages[idx]
    doc.__iter__ = lambda self: iter(pages)
    doc.__len__ = lambda self: num_pages
    doc.close = MagicMock()
    return doc


class TestRenderPdfPage:
    """Tests for render_pdf_page()."""

    @patch("app.core.pdf_renderer.fitz.open")
    def test_returns_image(self, mock_fitz_open):
        doc = _make_mock_doc(1)
        mock_fitz_open.return_value = doc
        result = render_pdf_page(Path("/fake.pdf"))
        assert isinstance(result, Image.Image)

    @patch("app.core.pdf_renderer.fitz.open")
    def test_closes_document(self, mock_fitz_open):
        doc = _make_mock_doc(1)
        mock_fitz_open.return_value = doc
        render_pdf_page(Path("/fake.pdf"))
        doc.close.assert_called_once()

    @patch("app.core.pdf_renderer.fitz.open")
    def test_closes_on_error(self, mock_fitz_open):
        doc = MagicMock()
        doc.__getitem__ = MagicMock(side_effect=RuntimeError("bad page"))
        doc.close = MagicMock()
        mock_fitz_open.return_value = doc
        with pytest.raises(RuntimeError):
            render_pdf_page(Path("/fake.pdf"))
        doc.close.assert_called_once()


class TestRenderAllPages:
    """Tests for render_all_pages()."""

    @patch("app.core.pdf_renderer.fitz.open")
    def test_returns_list_of_images(self, mock_fitz_open):
        doc = _make_mock_doc(3)
        mock_fitz_open.return_value = doc
        result = render_all_pages(Path("/fake.pdf"))
        assert len(result) == 3
        assert all(isinstance(img, Image.Image) for img in result)

    @patch("app.core.pdf_renderer.fitz.open")
    def test_closes_document(self, mock_fitz_open):
        doc = _make_mock_doc(2)
        mock_fitz_open.return_value = doc
        render_all_pages(Path("/fake.pdf"))
        doc.close.assert_called_once()


class TestGetPageCount:
    """Tests for get_page_count()."""

    @patch("app.core.pdf_renderer.fitz.open")
    def test_returns_count(self, mock_fitz_open):
        doc = _make_mock_doc(5)
        mock_fitz_open.return_value = doc
        assert get_page_count(Path("/fake.pdf")) == 5

    @patch("app.core.pdf_renderer.fitz.open")
    def test_closes_document(self, mock_fitz_open):
        doc = _make_mock_doc(1)
        mock_fitz_open.return_value = doc
        get_page_count(Path("/fake.pdf"))
        doc.close.assert_called_once()
