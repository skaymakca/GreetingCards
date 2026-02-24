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

    @pytest.mark.parametrize(
        "member,expected_color",
        [
            (Confidence.HIGH, "#34C759"),
            (Confidence.MEDIUM, "#FF9500"),
            (Confidence.LOW, "#FF3B30"),
            (Confidence.MANUAL, "#1E90FF"),
            (Confidence.NONE, "#6E6E73"),
        ],
    )
    def test_colors(self, member, expected_color):
        assert member.color() == expected_color

    @pytest.mark.parametrize("member", list(Confidence))
    def test_tooltip_non_empty(self, member):
        tooltip = member.tooltip()
        assert isinstance(tooltip, str)
        assert len(tooltip) > 0

    def test_all_members_have_colors(self):
        for member in Confidence:
            assert member.color().startswith("#")

    def test_all_members_have_tooltips(self):
        for member in Confidence:
            assert member.tooltip()


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
