"""Tests for app.core.card_processor standalone functions."""

import io
from pathlib import Path
from unittest.mock import patch

import pytest


class TestScanForPdfs:
    """Tests for scan_for_pdfs()."""

    def test_file_pdf(self, tmp_path):
        """Returns a single PDF file."""
        from app.core.card_processor import scan_for_pdfs

        pdf = tmp_path / "test.pdf"
        pdf.write_text("fake pdf")
        result = scan_for_pdfs(pdf)
        assert len(result) == 1
        assert result[0] == pdf.resolve()

    def test_file_non_pdf(self, tmp_path):
        """Returns empty list for non-PDF file."""
        from app.core.card_processor import scan_for_pdfs

        txt = tmp_path / "test.txt"
        txt.write_text("not a pdf")
        assert scan_for_pdfs(txt) == []

    def test_directory_recursive(self, tmp_path):
        """Recursively scans directory for PDFs."""
        from app.core.card_processor import scan_for_pdfs

        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "a.pdf").write_text("fake")
        (sub / "b.pdf").write_text("fake")
        (sub / "c.txt").write_text("not pdf")

        result = scan_for_pdfs(tmp_path)
        assert len(result) == 2
        names = [p.name for p in result]
        assert "a.pdf" in names
        assert "b.pdf" in names

    def test_case_insensitive(self, tmp_path):
        """Finds .PDF files case-insensitively."""
        from app.core.card_processor import scan_for_pdfs

        (tmp_path / "upper.PDF").write_text("fake")
        result = scan_for_pdfs(tmp_path)
        assert len(result) == 1

    def test_directory_sorted(self, tmp_path):
        """Results are sorted."""
        from app.core.card_processor import scan_for_pdfs

        (tmp_path / "z.pdf").write_text("fake")
        (tmp_path / "a.pdf").write_text("fake")
        result = scan_for_pdfs(tmp_path)
        assert result == sorted(result)


class TestWorkerResultToCard:
    """Tests for worker_result_to_card()."""

    def _make_worker_result(self, **kwargs):
        from app.models.card import PdfWorkerResult

        defaults: dict[str, object] = {
            "pdf_path": "/test/card.pdf",
            "file_hash": "abc123",
            "family_name": "Smith",
            "confidence": "high",
            "method": "ocr",
        }
        defaults.update(kwargs)
        return PdfWorkerResult(**defaults)

    def test_basic_conversion(self):
        """Converts PdfWorkerResult to CardResult correctly."""
        from PIL import Image

        from app.core.card_processor import worker_result_to_card
        from app.models.card import Confidence

        img = Image.new("RGB", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        wr = self._make_worker_result(
            preview_image_bytes=img_bytes,
            page_images_bytes=[img_bytes],
            alternates=["Smyth"],
        )
        card = worker_result_to_card(wr, card_id=1)

        assert card.id == 1
        assert card.filename == "card.pdf"
        assert card.file_hash == "abc123"
        assert card.family_name == "Smith"
        assert card.confidence == Confidence.HIGH
        assert card.preview_image is not None
        assert len(card.page_images) == 1

    def test_invalid_confidence_falls_back(self):
        """Invalid confidence string falls back to NONE."""
        from app.core.card_processor import worker_result_to_card
        from app.models.card import Confidence

        wr = self._make_worker_result(confidence="invalid_value")
        card = worker_result_to_card(wr, card_id=0)
        assert card.confidence == Confidence.NONE

    def test_error_sets_none_confidence(self):
        """Error field sets confidence=NONE and preserves error message."""
        from app.core.card_processor import worker_result_to_card
        from app.models.card import Confidence

        wr = self._make_worker_result(error="Something broke", confidence="high")
        card = worker_result_to_card(wr, card_id=0)
        assert card.error == "Something broke"
        assert card.confidence == Confidence.NONE

    def test_null_hash_becomes_empty_string(self):
        """None file_hash becomes empty string."""
        from app.core.card_processor import worker_result_to_card

        wr = self._make_worker_result(file_hash=None, error="Failed")
        card = worker_result_to_card(wr, card_id=1)
        assert card.file_hash == ""


class TestDeriveFolders:
    """Tests for derive_folders()."""

    def test_sorted_unique(self):
        """Returns sorted unique parent directories."""
        from app.core.card_processor import derive_folders
        from app.models.card import CardResult

        folder_a = Path("/test/aaa")
        folder_b = Path("/test/bbb")

        card1 = CardResult(id=0, file_paths=[folder_b / "x.pdf"], primary_path=folder_b / "x.pdf")
        card2 = CardResult(id=1, file_paths=[folder_a / "y.pdf"], primary_path=folder_a / "y.pdf")
        card3 = CardResult(id=2, file_paths=[folder_b / "z.pdf"], primary_path=folder_b / "z.pdf")

        result = derive_folders([card1, card2, card3])
        assert result == [folder_a, folder_b]

    def test_empty(self):
        """Returns empty list for no cards."""
        from app.core.card_processor import derive_folders

        assert derive_folders([]) == []


class TestLoadCardStateFromDb:
    """Tests for load_card_state_from_db()."""

    def test_no_hash_sets_none_confidence(self):
        """Sets NONE confidence and ai_analyzed=True when no hash."""
        from app.core.card_processor import load_card_state_from_db
        from app.models.card import CardResult, Confidence

        card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
        card.file_hash = ""

        load_card_state_from_db(card)
        assert card.confidence == Confidence.NONE
        assert card.ai_analyzed is True

    def test_with_state_populates_card(self):
        """Populates card fields from DB state."""
        from app.core.card_processor import load_card_state_from_db
        from app.models.card import CandidateInfo, CardResult, CardState, Confidence

        card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
        card.file_hash = "abc123"

        mock_state = CardState(
            display_name="Smith",
            method="ai",
            confidence="high",
            candidates=[CandidateInfo(id=1, family_name="Smith", method="ai", confidence="high")],
            remove_family=True,
            selected_candidate_id=1,
        )

        with patch("app.core.card_processor.get_card_state", return_value=mock_state):
            load_card_state_from_db(card)

        assert card.family_name == "Smith"
        assert card.confidence == Confidence.HIGH
        assert card.method == "ai"
        assert card.remove_family is True
        assert card.ai_analyzed is True
        assert card.manual_override == ""

    def test_no_state_resets_card(self):
        """Resets card to clean state when no DB record found."""
        from app.core.card_processor import load_card_state_from_db
        from app.models.card import CardResult, Confidence

        card = CardResult(id=0, file_paths=[Path("/test.pdf")], primary_path=Path("/test.pdf"))
        card.file_hash = "abc123"

        with patch("app.core.card_processor.get_card_state", return_value=None):
            load_card_state_from_db(card)

        assert card.ai_analyzed is True
        assert card.confidence == Confidence.NONE
        assert card.method == "missing"
