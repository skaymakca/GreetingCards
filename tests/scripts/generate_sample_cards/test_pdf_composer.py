"""Tests for scripts/generate_sample_cards/pdf_composer.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz  # type: ignore[import-untyped]
from scripts.generate_sample_cards.pdf_composer import compose_pdf_from_images


def _make_fitz_mocks():
    """Return (mock_doc, mock_page, mock_pix) with appropriate chaining."""
    mock_page = MagicMock()
    mock_page.rect = MagicMock()

    mock_doc = MagicMock()
    mock_doc.new_page.return_value = mock_page

    mock_pix = MagicMock()
    mock_pix.alpha = False
    mock_pix.tobytes.return_value = b"fake jpeg"

    return mock_doc, mock_page, mock_pix


class TestComposePdfFromImages:
    def test_creates_one_page_per_image(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        img1.write_bytes(b"fake")
        img2.write_bytes(b"fake")
        output = tmp_path / "out.pdf"

        mock_doc, _, mock_pix = _make_fitz_mocks()

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap", return_value=mock_pix),
        ):
            compose_pdf_from_images([img1, img2], output)

        assert mock_doc.new_page.call_count == 2

    def test_lossless_does_not_use_pixmap(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"fake png data")
        output = tmp_path / "out.pdf"

        mock_doc, _, _ = _make_fitz_mocks()

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap") as mock_pixmap_cls,
        ):
            compose_pdf_from_images([img1], output, jpeg_quality=-1)

        mock_pixmap_cls.assert_not_called()

    def test_jpeg_uses_pixmap(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"fake png data")
        output = tmp_path / "out.pdf"

        mock_doc, _, mock_pix = _make_fitz_mocks()

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap", return_value=mock_pix) as mock_pixmap_cls,
        ):
            compose_pdf_from_images([img1], output, jpeg_quality=75)
            mock_pixmap_cls.assert_called()

    def test_alpha_channel_dropped_for_jpeg(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"fake png data")
        output = tmp_path / "out.pdf"

        mock_doc, _, _ = _make_fitz_mocks()

        mock_pix_alpha = MagicMock()
        mock_pix_alpha.alpha = True
        mock_pix_alpha.tobytes.return_value = b"jpeg"

        mock_pix_rgb = MagicMock()
        mock_pix_rgb.alpha = False
        mock_pix_rgb.tobytes.return_value = b"jpeg no alpha"

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap", side_effect=[mock_pix_alpha, mock_pix_rgb]) as mock_pixmap_cls,
        ):
            compose_pdf_from_images([img1], output, jpeg_quality=75)
            # Should have been called twice: once to open, once to drop alpha
            assert mock_pixmap_cls.call_count == 2

    def test_saves_document(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"fake")
        output = tmp_path / "out.pdf"

        mock_doc, _, mock_pix = _make_fitz_mocks()

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap", return_value=mock_pix),
        ):
            compose_pdf_from_images([img1], output)

        mock_doc.save.assert_called_once()

    def test_closes_document(self, tmp_path: Path) -> None:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"fake")
        output = tmp_path / "out.pdf"

        mock_doc, _, mock_pix = _make_fitz_mocks()

        with (
            patch.object(fitz, "open", return_value=mock_doc),
            patch.object(fitz, "Pixmap", return_value=mock_pix),
        ):
            compose_pdf_from_images([img1], output)

        mock_doc.close.assert_called_once()
