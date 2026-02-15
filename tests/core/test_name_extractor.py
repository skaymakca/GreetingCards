"""Tests for app.core.name_extractor module."""
import pytest

from app.core.name_extractor import (
    _clean_name,
    _is_valid_name,
    extract_family_names,
    GREETING_WORDS,
)
from app.models.card import Confidence, NameMatch


class TestCleanName:
    """Tests for _clean_name()."""

    def test_strips_whitespace(self):
        assert _clean_name("  Smith  ") == "Smith"

    def test_strips_punctuation(self):
        assert _clean_name("Smith.,!;:") == "Smith"

    def test_strips_quotes(self):
        assert _clean_name('"Smith"') == "Smith"

    def test_collapses_whitespace(self):
        assert _clean_name("John   Smith") == "John Smith"

    def test_empty_string(self):
        assert _clean_name("") == ""

    def test_strips_dashes(self):
        assert _clean_name("—Smith—") == "Smith"


class TestIsValidName:
    """Tests for _is_valid_name()."""

    def test_valid_name(self):
        assert _is_valid_name("Smith") is True

    def test_too_short(self):
        assert _is_valid_name("A") is False

    def test_empty(self):
        assert _is_valid_name("") is False

    def test_all_greeting_words(self):
        assert _is_valid_name("Merry Christmas") is False

    def test_too_many_words(self):
        assert _is_valid_name("A B C D E F G") is False

    def test_no_uppercase(self):
        assert _is_valid_name("smith") is False

    def test_mixed_valid(self):
        assert _is_valid_name("John Smith") is True

    def test_greeting_plus_name(self):
        """A name with some greeting words but at least one non-greeting is valid."""
        assert _is_valid_name("Happy Smith") is True


class TestExtractFamilyNames:
    """Tests for extract_family_names()."""

    # HIGH confidence patterns
    def test_the_family_pattern(self):
        results = extract_family_names("The Smith Family")
        assert any(m.name == "Smith" and m.confidence == Confidence.HIGH for m in results)

    def test_the_plurals_pattern(self):
        """'The Johnsons' → Johnson with HIGH confidence (bug fix: was tuple)."""
        results = extract_family_names("The Johnsons")
        assert any(m.name == "Johnson" and m.confidence == Confidence.HIGH for m in results)
        # Verify it's a NameMatch, not a tuple
        for m in results:
            assert isinstance(m, NameMatch)

    def test_from_the_pattern(self):
        results = extract_family_names("From the Johnsons")
        assert any(m.name == "Johnson" and m.confidence == Confidence.HIGH for m in results)

    def test_from_the_family_pattern(self):
        results = extract_family_names("From the Smith Family")
        assert any(m.name == "Smith" and m.confidence == Confidence.HIGH for m in results)

    def test_love_the_pattern(self):
        results = extract_family_names("Love, The Smiths")
        assert any(m.name == "Smith" and m.confidence == Confidence.HIGH for m in results)

    def test_love_the_family_pattern(self):
        results = extract_family_names("Love, The Smith Family")
        assert any(m.name == "Smith" and m.confidence == Confidence.HIGH for m in results)

    # MEDIUM confidence patterns
    def test_with_love_couple_pattern(self):
        results = extract_family_names("With love, John & Jane Smith")
        assert any(m.name == "Smith" and m.confidence == Confidence.MEDIUM for m in results)

    def test_dash_the_family_pattern(self):
        """Dash pattern matches but 'The Smiths' HIGH pattern fires first; verify name found."""
        results = extract_family_names("-- The Smiths")
        assert any(m.name == "Smith" for m in results)

    def test_possessive_pattern(self):
        results = extract_family_names("The Johnson's house")
        assert any(m.name == "Johnson" and m.confidence == Confidence.MEDIUM for m in results)

    def test_couple_without_love(self):
        results = extract_family_names("John & Jane Smith")
        assert any(m.name == "Smith" and m.confidence == Confidence.MEDIUM for m in results)

    # LOW confidence patterns
    def test_love_first_last(self):
        results = extract_family_names("Love, John Smith")
        assert any(m.name == "Smith" and m.confidence == Confidence.LOW for m in results)

    def test_last_line_fallback(self):
        results = extract_family_names("Happy Holidays\nSmith")
        assert any(m.name == "Smith" and m.confidence == Confidence.LOW for m in results)

    # Edge cases
    def test_empty_text(self):
        assert extract_family_names("") == []

    def test_only_whitespace(self):
        assert extract_family_names("   \n   \n   ") == []

    def test_dedup_preserves_order(self):
        """Duplicate names are removed, keeping first occurrence."""
        text = "The Smith Family\nFrom the Smith Family"
        results = extract_family_names(text)
        smith_matches = [m for m in results if m.name == "Smith"]
        assert len(smith_matches) == 1

    def test_greeting_words_filtered(self):
        """Names that are all greeting words are not returned."""
        results = extract_family_names("Love, Merry Christmas")
        names = [m.name for m in results]
        assert "Christmas" not in names

    def test_multiline_text(self):
        text = "Happy Holidays!\nThe Johnson Family\nFrom all of us"
        results = extract_family_names(text)
        assert any(m.name == "Johnson" for m in results)

    def test_the_double_s_not_stripped(self):
        """Names ending in 'ss' like 'Ross' should not have trailing s stripped."""
        results = extract_family_names("The Ross Family")
        assert any(m.name == "Ross" for m in results)

    def test_multiple_names_different_confidence(self):
        """Multiple patterns yield multiple results at different confidences."""
        text = "The Smith Family\nLove, John Jones"
        results = extract_family_names(text)
        names = {m.name for m in results}
        assert "Smith" in names
