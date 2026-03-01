"""Tests for app.models.card module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.card import (
    CandidateInfo,
    CardResult,
    CardState,
    Confidence,
    NameMatch,
    RenamePlanItem,
    RenameResult,
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

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_target_filename_with_family(self, mock_sanitize):
        card = CardResult(id=1, family_name="Smith")
        assert card.target_filename("2025") == "Holiday Cards 2025 - Smith Family.pdf"

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_target_filename_remove_family(self, mock_sanitize):
        card = CardResult(id=1, family_name="Smith", remove_family=True)
        assert card.target_filename("2025") == "Holiday Cards 2025 - Smith.pdf"

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_target_filename_already_ends_with_family(self, mock_sanitize):
        card = CardResult(id=1, family_name="Smith Family")
        assert card.target_filename("2025") == "Holiday Cards 2025 - Smith Family.pdf"

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_target_filename_empty_name(self, mock_sanitize):
        card = CardResult(id=1)
        assert card.target_filename("2025") == ""

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_target_filename_manual_override(self, mock_sanitize):
        card = CardResult(id=1, family_name="Smith", manual_override="Jones")
        assert card.target_filename("2025") == "Holiday Cards 2025 - Jones Family.pdf"


class TestTargetFilenameValidation:
    """Tests for target_filename year validation (new behavior)."""

    def test_empty_year_returns_empty(self):
        """Empty year string should return empty string."""
        card = CardResult(id=1, family_name="Smith", confidence=Confidence.HIGH)
        assert card.target_filename("") == ""

    def test_whitespace_year_returns_empty(self):
        """Whitespace-only year should return empty string."""
        card = CardResult(id=1, family_name="Smith", confidence=Confidence.HIGH)
        assert card.target_filename("   ") == ""

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_year_is_stripped(self, mock_sanitize):
        """Year with surrounding whitespace should be stripped."""
        card = CardResult(id=1, family_name="Smith", confidence=Confidence.HIGH)
        result = card.target_filename(" 2024 ")
        assert result == "Holiday Cards 2024 - Smith Family.pdf"

    @patch("app.models.card.sanitize_for_filename", side_effect=lambda x: x)
    def test_normal_year(self, mock_sanitize):
        """Normal year produces correct filename."""
        card = CardResult(id=1, family_name="Smith", confidence=Confidence.HIGH)
        assert card.target_filename("2024") == "Holiday Cards 2024 - Smith Family.pdf"


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
