"""Tests for name formatting utilities (filename sanitization)."""

import pytest

from app.core.name_formatting import sanitize_for_filename


class TestSanitizeForFilename:
    """Tests for sanitizing filenames by replacing invalid characters."""

    def test_replaces_backslash(self):
        """Should replace backslash with dash."""
        assert sanitize_for_filename("test\\file") == "test-file"

    def test_replaces_forward_slash(self):
        """Should replace forward slash with dash."""
        assert sanitize_for_filename("test/file") == "test-file"

    def test_replaces_colon(self):
        """Should replace colon with dash."""
        assert sanitize_for_filename("test:file") == "test-file"

    def test_replaces_asterisk(self):
        """Should replace asterisk with dash."""
        assert sanitize_for_filename("test*file") == "test-file"

    def test_replaces_question_mark(self):
        """Should replace question mark with dash."""
        assert sanitize_for_filename("test?file") == "test-file"

    def test_replaces_double_quote(self):
        """Should replace double quote with dash."""
        assert sanitize_for_filename('test"file') == "test-file"

    def test_replaces_angle_brackets(self):
        """Should replace angle brackets with dash."""
        assert sanitize_for_filename("test<file") == "test-file"
        assert sanitize_for_filename("test>file") == "test-file"
        assert sanitize_for_filename("test<file>") == "test-file-"

    def test_replaces_pipe(self):
        """Should replace pipe character with dash."""
        assert sanitize_for_filename("test|file") == "test-file"

    def test_multiple_invalid_chars(self):
        """Should replace multiple invalid characters."""
        assert sanitize_for_filename("test*file<name>") == "test-file-name-"
        assert sanitize_for_filename('test"file:name?') == "test-file-name-"

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

    def test_empty_string(self):
        """Should handle empty strings."""
        assert sanitize_for_filename("") == ""

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
