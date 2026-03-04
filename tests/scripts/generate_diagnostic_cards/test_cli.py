"""Tests for scripts/generate_diagnostic_cards/cli.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.generate_diagnostic_cards.cli import _create_diagnostic_pdf, main


class TestCreateDiagnosticPdf:
    def test_creates_pdf_via_fitz(self, tmp_path: Path) -> None:
        output_path = tmp_path / "test.pdf"

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake jpeg"

        mock_vector_doc = MagicMock()
        mock_vector_doc.new_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pix

        mock_final_doc = MagicMock()
        mock_final_page = MagicMock()
        mock_final_doc.new_page.return_value = mock_final_page

        # fitz.open() is called twice: once for vector_doc, once for final_doc
        open_calls = [mock_vector_doc, mock_final_doc]

        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = open_calls
        mock_fitz.Point.return_value = MagicMock()
        mock_fitz.get_text_length.return_value = 100.0

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            import importlib

            import scripts.generate_diagnostic_cards.cli as dc_mod

            importlib.reload(dc_mod)
            dc_mod._create_diagnostic_pdf("Smith", output_path)

        # Verify vector doc got a new page
        mock_vector_doc.new_page.assert_called_once()
        # Verify text was inserted
        mock_page.insert_text.assert_called_once()
        # Verify pixmap was obtained
        mock_page.get_pixmap.assert_called_once()
        # Verify final doc was saved
        mock_final_doc.save.assert_called_once()


class TestMain:
    def test_requires_names_argument(self) -> None:
        with patch("sys.argv", ["generate_diagnostic_cards"]), pytest.raises(SystemExit):
            main()

    def test_exits_with_empty_names(self) -> None:
        with patch("sys.argv", ["prog", "--names", "  ,  , ", "--no-open"]), pytest.raises(SystemExit):
            main()

    def test_calls_create_pdf_for_each_name(self, tmp_path: Path) -> None:
        with (
            patch("sys.argv", ["prog", "--names", "Smith,Jones", "--no-open"]),
            patch("scripts.generate_diagnostic_cards.cli._create_diagnostic_pdf") as mock_create,
            patch("scripts.generate_diagnostic_cards.cli.script_output_dir") as mock_ctx,
        ):
            mock_ctx.return_value.__enter__ = lambda s: tmp_path
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Create fake output files so stat() works
            (tmp_path / "The Smith Family.pdf").write_bytes(b"fake")
            (tmp_path / "The Jones Family.pdf").write_bytes(b"fake")

            main()

        assert mock_create.call_count == 2

    def test_opens_finder_on_completion(self, tmp_path: Path) -> None:
        """Without --no-open, subprocess.run is called with 'open'."""
        with (
            patch("sys.argv", ["prog", "--names", "Smith"]),
            patch("scripts.generate_diagnostic_cards.cli._create_diagnostic_pdf"),
            patch("scripts.generate_diagnostic_cards.cli.script_output_dir") as mock_ctx,
            patch("scripts.generate_diagnostic_cards.cli.subprocess.run") as mock_run,
        ):
            mock_ctx.return_value.__enter__ = lambda s: tmp_path
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            (tmp_path / "The Smith Family.pdf").write_bytes(b"fake")

            main()

        mock_run.assert_called_once_with(["open", str(tmp_path)], check=False)

    def test_open_finder_not_found_no_crash(self, tmp_path: Path) -> None:
        """FileNotFoundError from 'open' is silently caught."""
        with (
            patch("sys.argv", ["prog", "--names", "Smith"]),
            patch("scripts.generate_diagnostic_cards.cli._create_diagnostic_pdf"),
            patch("scripts.generate_diagnostic_cards.cli.script_output_dir") as mock_ctx,
            patch("scripts.generate_diagnostic_cards.cli.subprocess.run", side_effect=FileNotFoundError),
        ):
            mock_ctx.return_value.__enter__ = lambda s: tmp_path
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            (tmp_path / "The Smith Family.pdf").write_bytes(b"fake")

            # Should not raise
            main()
