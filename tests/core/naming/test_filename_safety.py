"""Tests for filename safety utilities (sanitize_for_filename and related constants)."""

import pytest

from app.core.naming.family_name import clean_and_filter_family_names
from app.core.naming.filename_safety import _INVALID_FS_CHARS, INVALID_FILENAME_CHARS, sanitize_for_filename
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

    def test_strips_leading_whitespace(self):
        """Should strip leading whitespace."""
        assert sanitize_for_filename("   test") == "test"
        assert sanitize_for_filename("\ttest") == "test"
        assert sanitize_for_filename("\ntest") == "test"

    def test_strips_trailing_whitespace(self):
        """Should strip trailing whitespace."""
        assert sanitize_for_filename("test   ") == "test"
        assert sanitize_for_filename("test\t") == "test"
        assert sanitize_for_filename("test\n") == "test"

    def test_strips_leading_and_trailing_whitespace(self):
        """Should strip both leading and trailing whitespace."""
        assert sanitize_for_filename("   test name   ") == "test name"
        assert sanitize_for_filename("\t  test  \n") == "test"

    def test_clean_name_unchanged(self):
        """Should leave clean names unchanged."""
        assert sanitize_for_filename("test_file") == "test_file"
        assert sanitize_for_filename("test-file") == "test-file"
        assert sanitize_for_filename("test.file") == "test.file"
        assert sanitize_for_filename("TestFile") == "TestFile"

    def test_clean_name_with_numbers(self):
        """Should preserve numbers and alphanumeric names."""
        assert sanitize_for_filename("test123") == "test123"
        assert sanitize_for_filename("123test") == "123test"
        assert sanitize_for_filename("test_file_123") == "test_file_123"

    def test_whitespace_only_string(self):
        """Should return empty string for whitespace-only input."""
        assert sanitize_for_filename("   ") == ""
        assert sanitize_for_filename("\t\n") == ""

    def test_only_invalid_chars(self):
        """Should replace all invalid chars with dashes."""
        assert sanitize_for_filename("*?<>") == "----"
        assert sanitize_for_filename('\\/:*?"<>|') == "---------"

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("My File*", "My File-"),
            ("C:\\Users\\test", "C--Users-test"),
            ("Report?Q1", "Report-Q1"),
            ('Invoice "2024"', "Invoice -2024-"),
            ("Important|Urgent", "Important-Urgent"),
            ("  Trim  Me  ", "Trim  Me"),
        ],
    )
    def test_sanitize_various_cases(self, input_str, expected):
        """Parameterized test for various sanitization cases."""
        assert sanitize_for_filename(input_str) == expected


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
        result = clean_and_filter_family_names(["Smith/Jones"])
        assert len(result) == 1
        assert "/" not in result[0]
        assert "-" in result[0]
