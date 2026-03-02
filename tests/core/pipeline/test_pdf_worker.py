"""Tests for app.core.pipeline.pdf_worker module."""

from dataclasses import fields
from unittest.mock import patch

import pytest
from PIL import Image

from app.core.pipeline.pdf_worker import process_pdf_worker
from app.models.card import CandidateInfo, CardState, PdfWorkerResult


def _make_test_image(width=10, height=10, color="red"):
    """Create a small test PIL Image."""
    return Image.new("RGB", (width, height), color)


class TestProcessPdfWorkerSuccess:
    """Tests for successful PDF processing paths."""

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="OCR text here")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_new_pdf_runs_ocr_and_saves(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """New PDF (no cached state) runs OCR, saves raw, and reprocesses."""
        mock_render.return_value = [_make_test_image()]
        # First call: no cached state; second call: after processing
        mock_state.side_effect = [
            None,
            CardState(
                display_name="Smith",
                method="ocr",
                confidence="high",
                candidates=[],
                remove_family=False,
                selected_candidate_id=None,
            ),
        ]

        result = process_pdf_worker("/fake/card.pdf")

        assert result.file_hash == "abc123"
        assert result.family_name == "Smith"
        assert not result.error
        mock_ocr.assert_called_once()
        mock_save.assert_called_once_with("abc123", "OCR text here")
        assert mock_reprocess.call_count == 1

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_cached_pdf_skips_ocr(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """Cached PDF (existing state) skips OCR, only reprocesses candidates."""
        mock_render.return_value = [_make_test_image()]
        cached_state = CardState(
            display_name="Jones",
            method="ocr",
            confidence="high",
            candidates=[],
            remove_family=False,
            selected_candidate_id=None,
        )
        mock_state.return_value = cached_state

        result = process_pdf_worker("/fake/card.pdf")

        assert result.family_name == "Jones"
        mock_ocr.assert_not_called()
        mock_save.assert_not_called()
        mock_reprocess.assert_called_once_with("abc123")

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="text")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_result_is_dataclass_with_expected_fields(
        self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess
    ):
        """Result is a PdfWorkerResult with all expected fields."""
        mock_render.return_value = [_make_test_image()]
        mock_state.side_effect = [None, None]

        result = process_pdf_worker("/fake/card.pdf")

        assert isinstance(result, PdfWorkerResult)
        expected_fields = {f.name for f in fields(PdfWorkerResult)}
        actual_fields = {f.name for f in fields(result)}
        assert actual_fields == expected_fields


class TestProcessPdfWorkerImageHandling:
    """Tests for image serialization in the worker."""

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="")
    @patch("app.core.pipeline.pdf_worker.render_all_pages", return_value=[])
    @patch("app.core.pipeline.pdf_worker.get_card_state", return_value=None)
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_empty_images_no_preview(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """When render returns empty list, preview and page bytes are None/empty."""
        result = process_pdf_worker("/fake/card.pdf")

        assert result.preview_image_bytes is None
        assert result.page_images_bytes == []
        # No OCR should be called since no images
        mock_ocr.assert_not_called()

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="text")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_single_image_as_png_bytes(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """Single image is serialized as PNG bytes."""
        mock_render.return_value = [_make_test_image()]
        mock_state.side_effect = [None, None]

        result = process_pdf_worker("/fake/card.pdf")

        assert result.preview_image_bytes is not None
        # Verify it's valid PNG
        assert result.preview_image_bytes[:4] == b"\x89PNG"
        assert len(result.page_images_bytes) == 1
        assert result.page_images_bytes[0][:4] == b"\x89PNG"

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="text")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_multiple_images_as_png_bytes(
        self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess
    ):
        """Multiple images all serialized as PNG bytes."""
        mock_render.return_value = [_make_test_image(), _make_test_image(), _make_test_image()]
        mock_state.side_effect = [None, None]

        result = process_pdf_worker("/fake/card.pdf")

        assert len(result.page_images_bytes) == 3
        for page_bytes in result.page_images_bytes:
            assert page_bytes[:4] == b"\x89PNG"


class TestProcessPdfWorkerErrors:
    """Tests for error handling in the worker."""

    @patch("app.core.pipeline.pdf_worker.compute_file_hash", side_effect=OSError("disk error"))
    def test_hash_error(self, mock_hash):
        """Hash computation error is captured in result."""
        result = process_pdf_worker("/fake/card.pdf")

        assert result.error == "disk error"
        assert result.file_hash is None

    @patch("app.core.pipeline.pdf_worker.render_all_pages", side_effect=RuntimeError("render failed"))
    @patch("app.core.pipeline.pdf_worker.get_card_state", return_value=None)
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_render_error(self, mock_hash, mock_state, mock_render):
        """Render error is captured in result."""
        result = process_pdf_worker("/fake/card.pdf")

        assert result.error == "render failed"
        assert result.file_hash == "abc123"

    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", side_effect=RuntimeError("OCR failed"))
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state", return_value=None)
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_ocr_error(self, mock_hash, mock_state, mock_render, mock_ocr):
        """OCR error is captured in result."""
        mock_render.return_value = [_make_test_image()]

        result = process_pdf_worker("/fake/card.pdf")

        assert result.error == "OCR failed"

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw", side_effect=RuntimeError("reprocess failed"))
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_reprocess_error(self, mock_hash, mock_state, mock_render, mock_reprocess):
        """Reprocess error for cached card is captured in result."""
        mock_render.return_value = [_make_test_image()]
        cached_state = CardState(
            display_name="Smith",
            method="ocr",
            confidence="high",
            candidates=[],
            remove_family=False,
            selected_candidate_id=None,
        )
        mock_state.return_value = cached_state

        result = process_pdf_worker("/fake/card.pdf")

        assert result.error == "reprocess failed"


class TestProcessPdfWorkerCardState:
    """Tests for card state mapping in results."""

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="text")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_card_state_maps_to_result(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """CardState fields are correctly mapped to result."""
        mock_render.return_value = [_make_test_image()]
        candidate = CandidateInfo(id=42, family_name="Smith", method="ai", confidence="high")
        state = CardState(
            display_name="Smith",
            method="ai",
            confidence="high",
            candidates=[candidate],
            remove_family=True,
            selected_candidate_id=42,
        )
        mock_state.side_effect = [None, state]

        result = process_pdf_worker("/fake/card.pdf")

        assert result.family_name == "Smith"
        assert result.confidence == "high"
        assert result.method == "ai"
        assert result.candidates == [candidate]
        assert result.remove_family is True
        assert result.selected_candidate_id == 42

    @patch("app.core.pipeline.pdf_worker.reprocess_candidates_from_raw")
    @patch("app.core.pipeline.pdf_worker.save_raw_ocr")
    @patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="text")
    @patch("app.core.pipeline.pdf_worker.render_all_pages")
    @patch("app.core.pipeline.pdf_worker.get_card_state")
    @patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="abc123")
    def test_none_state_gives_defaults(self, mock_hash, mock_state, mock_render, mock_ocr, mock_save, mock_reprocess):
        """When get_card_state returns None after processing, defaults are kept."""
        mock_render.return_value = [_make_test_image()]
        mock_state.return_value = None

        result = process_pdf_worker("/fake/card.pdf")

        assert result.family_name == ""
        assert result.confidence == "none"
        assert result.method == "missing"
        assert result.remove_family is False
        assert result.selected_candidate_id is None


class TestProcessPdfWorkerWithDB:
    """DB-backed tests for process_pdf_worker using real in-memory SQLite."""

    @pytest.fixture(autouse=True)
    def _use_db(self, in_memory_db):
        return in_memory_db

    def test_new_pdf_saves_ocr_and_creates_candidates(self):
        """New PDF saves OCR text and creates OCR candidates in the DB."""
        from app.core.database import get_candidates, get_raw_ocr

        test_image = _make_test_image()
        with (
            patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="h1"),
            patch("app.core.pipeline.pdf_worker.render_all_pages", return_value=[test_image]),
            patch("app.core.pipeline.pdf_worker.extract_text_all_pages", return_value="The Smith Family"),
        ):
            result = process_pdf_worker("/tmp/test.pdf")

        assert not result.error
        assert get_raw_ocr("h1") == "The Smith Family"
        candidates = get_candidates("h1")
        assert any(c.method == "ocr" and c.family_name == "Smith" for c in candidates)

    def test_cached_pdf_reprocesses_without_ocr(self):
        """Cached PDF skips OCR but reprocesses candidates from existing raw data."""
        from app.core.database import create_or_update_card, get_raw_ocr, save_raw_ocr

        create_or_update_card("h1")
        save_raw_ocr("h1", "The Old Family")

        test_image = _make_test_image()
        with (
            patch("app.core.pipeline.pdf_worker.compute_file_hash", return_value="h1"),
            patch("app.core.pipeline.pdf_worker.render_all_pages", return_value=[test_image]),
            patch("app.core.pipeline.pdf_worker.extract_text_all_pages") as mock_ocr,
        ):
            result = process_pdf_worker("/tmp/test.pdf")

        mock_ocr.assert_not_called()
        assert not result.error
        assert get_raw_ocr("h1") == "The Old Family"
