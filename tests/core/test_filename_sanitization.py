"""Tests for filename sanitization in the name cleaning pipeline."""

import pytest
from app.core.name_formatting import sanitize_for_filename, INVALID_FILENAME_CHARS, _INVALID_FS_CHARS
from app.core.database import _clean_and_filter_names
from app.models.card import CardResult, Confidence


class TestSanitizeForFilename:
    """Tests for sanitize_for_filename()."""

    def test_forward_slash(self):
        assert sanitize_for_filename("Smith/Jones") == "Smith-Jones"

    def test_backslash(self):
        assert sanitize_for_filename("Smith\\Jones") == "Smith-Jones"

    def test_colon(self):
        assert sanitize_for_filename("Smith: Jones") == "Smith- Jones"

    def test_asterisk(self):
        assert sanitize_for_filename("Smith*") == "Smith-"

    def test_question_mark(self):
        assert sanitize_for_filename("Smith?") == "Smith-"

    def test_double_quote(self):
        assert sanitize_for_filename('Smith "Jr"') == "Smith -Jr-"

    def test_angle_brackets(self):
        assert sanitize_for_filename("Smith<Jones>") == "Smith-Jones-"

    def test_pipe(self):
        assert sanitize_for_filename("Smith|Jones") == "Smith-Jones"

    def test_clean_name_passes_through(self):
        assert sanitize_for_filename("O'Brien-McDonald") == "O'Brien-McDonald"

    def test_multiple_invalid_chars(self):
        assert sanitize_for_filename("A/B\\C:D") == "A-B-C-D"

    def test_empty_string(self):
        assert sanitize_for_filename("") == ""


class TestInvalidFilenameCharsConsistency:
    """Verify INVALID_FILENAME_CHARS frozenset matches _INVALID_FS_CHARS regex."""

    def test_frozenset_matches_regex(self):
        """Every char in INVALID_FILENAME_CHARS is matched by the regex."""
        for char in INVALID_FILENAME_CHARS:
            assert _INVALID_FS_CHARS.search(char), f"Regex should match '{char}'"

    def test_regex_does_not_match_valid_chars(self):
        """Common valid filename characters are not matched."""
        for char in "abcABC123-_. '()":
            assert not _INVALID_FS_CHARS.search(char), f"Regex should not match '{char}'"


class TestTargetFilenameSanitization:
    """Verify target_filename() sanitizes invalid characters."""

    def test_slash_in_family_name(self):
        card = CardResult(id=1, family_name="Smith/Jones", confidence=Confidence.HIGH)
        assert card.target_filename("2024") == "Holiday Cards 2024 - Smith-Jones Family.pdf"

    def test_backslash_in_manual_override(self):
        card = CardResult(id=1, manual_override="O'Brien\\Smith", confidence=Confidence.MANUAL)
        assert card.target_filename("2024") == "Holiday Cards 2024 - O'Brien-Smith Family.pdf"

    def test_sanitization_with_remove_family(self):
        card = CardResult(id=1, family_name="A<B>C", confidence=Confidence.HIGH, remove_family=True)
        assert card.target_filename("2024") == "Holiday Cards 2024 - A-B-C.pdf"

    def test_pipe_in_name(self):
        card = CardResult(id=1, family_name="Smith|Jones", confidence=Confidence.HIGH)
        assert card.target_filename("2024") == "Holiday Cards 2024 - Smith-Jones Family.pdf"


class TestCleanAndFilterIntegration:
    """Integration test: invalid chars removed through the full pipeline."""

    def test_slash_in_name_cleaned(self):
        """A slash from AI extraction should be replaced with dash."""
        result = _clean_and_filter_names(["Smith/Jones"])
        assert len(result) == 1
        assert "/" not in result[0]
        assert "-" in result[0]
