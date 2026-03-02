"""Tests for app.models.card module."""

from pathlib import Path

import pytest

from app.models.card import (
    CandidateInfo,
    CardResult,
    CardState,
    Confidence,
    NameMatch,
)


class TestConfidence:
    """Tests for Confidence enum."""

    @pytest.mark.parametrize(
        "member,value",
        [
            (Confidence.HIGH, "high"),
            (Confidence.MEDIUM, "medium"),
            (Confidence.LOW, "low"),
            (Confidence.MANUAL, "manual"),
            (Confidence.NONE, "none"),
        ],
    )
    def test_values(self, member, value):
        assert member.value == value


class TestCandidateInfo:
    """Tests for CandidateInfo dataclass."""

    def test_creation(self):
        c = CandidateInfo(id=1, family_name="Smith", method="ocr", confidence="high")
        assert c.id == 1
        assert c.family_name == "Smith"
        assert c.method == "ocr"
        assert c.confidence == "high"

    def test_display_label(self):
        c = CandidateInfo(id=1, family_name="Smith", method="ocr", confidence="high")
        assert c.display_label == "Smith (OCR - High)"

    def test_display_label_ai_medium(self):
        c = CandidateInfo(id=2, family_name="Jones", method="ai", confidence="medium")
        assert c.display_label == "Jones (AI - Medium)"


class TestCardState:
    """Tests for CardState dataclass."""

    def test_creation(self):
        cs = CardState(
            display_name="Smith",
            method="manual",
            confidence="manual",
            candidates=[],
            remove_family=False,
            selected_candidate_id=None,
        )
        assert cs.display_name == "Smith"
        assert cs.method == "manual"


class TestNameMatch:
    """Tests for NameMatch dataclass."""

    def test_creation(self):
        nm = NameMatch(name="Johnson", confidence=Confidence.HIGH)
        assert nm.name == "Johnson"
        assert nm.confidence == Confidence.HIGH


class TestCardResult:
    """Tests for CardResult dataclass."""

    def test_defaults(self):
        card = CardResult(id=1)
        assert card.id == 1
        assert card.family_name == ""
        assert card.confidence == Confidence.NONE
        assert card.file_paths == []
        assert card.candidates == []
        assert card.manual_override == ""
        assert card.ai_analyzed is False
        assert card.remove_family is False
        assert card.error == ""

    def test_display_name_family_name(self):
        card = CardResult(id=1, family_name="Smith")
        assert card.display_name == "Smith"

    def test_display_name_manual_override(self):
        card = CardResult(id=1, family_name="Smith", manual_override="Jones")
        assert card.display_name == "Jones"

    def test_filename_property(self):
        card = CardResult(id=1, primary_path=Path("/cards/test.pdf"))
        assert card.filename == "test.pdf"

    def test_pdf_path_backward_compat(self):
        p = Path("/cards/test.pdf")
        card = CardResult(id=1, primary_path=p)
        assert card.pdf_path == p


class TestPrimaryPathDefault:
    """Tests for primary_path default value."""

    def test_default_is_empty_path(self):
        """Default primary_path should be Path(''), not current directory."""
        card = CardResult(id=1)
        assert card.primary_path == Path("")
        assert card.primary_path.name == ""


class TestPdfWorkerResultErrorDefault:
    """Tests for PdfWorkerResult error field standardization."""

    def test_error_default_is_empty_string(self):
        """Default error should be empty string (falsy)."""
        from app.models.card import PdfWorkerResult

        result = PdfWorkerResult(pdf_path="/test.pdf")
        assert result.error == ""
        assert not result.error
