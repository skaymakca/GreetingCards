"""Tests for app.core.family_name.cleaning module."""

import pytest

from app.core.family_name.cleaning import (
    clean_and_filter_family_names,
    clean_family_name,
    strip_family_name_punctuation,
    strip_plural_family_name,
)


class TestStripPluralFamilyName:
    """Tests for strip_plural_family_name() — data-driven + heuristic."""

    # Preserved by Census data
    @pytest.mark.parametrize(
        "name",
        ["Morales", "Torres", "Jones", "Williams", "Adams", "Davis", "Thomas", "Harris", "Rogers"],
    )
    def test_preserves_census_names(self, name):
        assert strip_plural_family_name(name) == name

    # Case-insensitive database lookup
    def test_preserves_census_case_insensitive(self):
        assert strip_plural_family_name("MORALES") == "MORALES"
        assert strip_plural_family_name("morales") == "morales"

    # Non-Census DB names also preserved (from Faker/smashew)
    def test_preserves_non_census_db_names(self):
        """Names from Faker/smashew (rank=0) are still preserved."""
        assert strip_plural_family_name("Browns") == "Browns"
        assert strip_plural_family_name("Stewarts") == "Stewarts"

    # Heuristic: sibilant 'es' stripping
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Walshes", "Walsh"),
            ("Marches", "March"),
            ("Foxes", "Fox"),
        ],
    )
    def test_strips_sibilant_es(self, input_name, expected):
        assert strip_plural_family_name(input_name) == expected

    # Heuristic: consonant-pair 's' stripping (names NOT in the DB)
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Smiths", "Smith"),
            ("Brockhurts", "Brockhurt"),
            ("Wentworths", "Wentworth"),
        ],
    )
    def test_strips_consonant_pair_s(self, input_name, expected):
        assert strip_plural_family_name(input_name) == expected

    # Double 'ss' preserved
    def test_preserves_double_ss(self):
        assert strip_plural_family_name("Ross") == "Ross"
        assert strip_plural_family_name("Cross") == "Cross"
        assert strip_plural_family_name("Bass") == "Bass"

    # Short names preserved
    def test_preserves_short_names(self):
        assert strip_plural_family_name("As") == "As"
        assert strip_plural_family_name("Ab") == "Ab"

    # Edge cases
    def test_empty_string(self):
        assert strip_plural_family_name("") == ""

    def test_non_strip_consonant_pattern(self):
        assert strip_plural_family_name("Clarks") == "Clarks"  # -rks not in strip set


class TestCleanFamilyName:
    """Tests for clean_family_name()."""

    def test_removes_the(self):
        assert "The" not in clean_family_name("The Smith")

    def test_removes_family(self):
        assert "Family" not in clean_family_name("Smith Family")

    def test_removes_from_prefix(self):
        assert "From:" not in clean_family_name("From: Smith")

    def test_removes_sent_by(self):
        assert "Sent by:" not in clean_family_name("Sent by: Smith")

    def test_removes_quotes(self):
        result = clean_family_name('"Smith"')
        assert '"' not in result
        assert result == "Smith"

    def test_removes_smart_quotes(self):
        result = clean_family_name("\u201cSmith\u201d")
        assert result == "Smith"

    def test_strips_punctuation(self):
        assert clean_family_name("Smith.,!") == "Smith"

    def test_removes_colon_prefix(self):
        assert clean_family_name("Name: Smith") == "Smith"

    def test_empty_string(self):
        assert clean_family_name("") == ""

    def test_strips_plural(self):
        assert clean_family_name("Smiths") == "Smith"

    def test_full_cleanup(self):
        result = clean_family_name('The "Smiths" Family')
        assert result == "Smith"


class TestStripFamilyNamePunctuation:
    """Tests for strip_family_name_punctuation()."""

    def test_strips_trailing_punctuation(self):
        assert strip_family_name_punctuation("Smith.,!") == "Smith"

    def test_strips_leading_punctuation(self):
        assert strip_family_name_punctuation("--Smith") == "Smith"

    def test_collapses_whitespace(self):
        assert strip_family_name_punctuation("John   Smith") == "John Smith"

    def test_strips_quotes(self):
        assert strip_family_name_punctuation('"Smith"') == "Smith"

    def test_empty_string(self):
        assert strip_family_name_punctuation("") == ""


class TestCleanAndFilterFamilyNames:
    """Tests for clean_and_filter_family_names() — the pipeline."""

    def test_filters_unknown(self):
        result = clean_and_filter_family_names(["unknown", "Smith"])
        assert "Smith" in result
        assert not any(r.lower() == "unknown" for r in result)

    def test_filters_empty(self):
        result = clean_and_filter_family_names(["", "Smith"])
        assert len(result) == 1

    def test_filters_snapfish(self):
        assert clean_and_filter_family_names(["Snapfish"]) == []

    @pytest.mark.parametrize(
        "word",
        ["Family", "FAMILY", "family", "Holiday", "Greeting", "Christmas", "Minted"],
    )
    def test_filters_generic_card_words(self, word):
        result = clean_and_filter_family_names([word, "Smith"])
        assert len(result) == 1
        assert result[0] == "Smith"

    @pytest.mark.parametrize(
        "phrase",
        ["New Year", "Season's Greetings", "Chinese New Year", "Valentine's Day"],
    )
    def test_filters_multi_word_holiday_names(self, phrase):
        result = clean_and_filter_family_names([phrase])
        assert len(result) == 0

    def test_preserves_real_names(self):
        result = clean_and_filter_family_names(["Johnson", "Williams", "Morales"])
        assert len(result) == 3

    def test_cleans_then_filters(self):
        """Full pipeline: clean quotes/prefixes, then filter blocklist."""
        result = clean_and_filter_family_names(['"Family"', "The Smith"])
        # "Family" cleaned to "Family" then filtered out
        # "The Smith" cleaned to "Smith" which passes
        assert result == ["Smith"]

    def test_slash_in_name_cleaned(self):
        """Filesystem-invalid chars are replaced with dash."""
        result = clean_and_filter_family_names(["Smith/Jones"])
        assert len(result) == 1
        assert "/" not in result[0]
        assert "-" in result[0]
