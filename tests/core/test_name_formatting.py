"""Tests for name formatting utilities."""

import pytest

from app.core.name_formatting import deparameterize_name, smart_title_case


class TestDeparameterizeName:
    """Tests for removing plural 's' from family names."""

    @pytest.mark.unit
    def test_removes_plural_s(self):
        """Should remove plural 's' from simple family names."""
        assert deparameterize_name("Smiths") == "Smith"
        assert deparameterize_name("Browns") == "Brown"
        assert deparameterize_name("Millers") == "Miller"

    @pytest.mark.unit
    def test_preserves_names_ending_in_s(self):
        """Should keep names that naturally end in 's'."""
        assert deparameterize_name("Jones") == "Jones"
        assert deparameterize_name("Williams") == "Williams"
        assert deparameterize_name("Davis") == "Davis"

    @pytest.mark.unit
    def test_preserves_names_ending_in_ss(self):
        """Should keep names ending in double 's'."""
        assert deparameterize_name("Bass") == "Bass"
        assert deparameterize_name("Cross") == "Cross"

    @pytest.mark.unit
    def test_handles_the_prefix(self):
        """Should handle 'The' prefix correctly."""
        assert deparameterize_name("The Smiths") == "The Smith"
        assert deparameterize_name("The Jones") == "The Jones"

    @pytest.mark.unit
    def test_handles_short_names(self):
        """Should not modify short names (3 chars or less)."""
        assert deparameterize_name("Lys") == "Lys"
        assert deparameterize_name("Les") == "Les"

    @pytest.mark.unit
    def test_handles_empty_string(self):
        """Should handle empty strings gracefully."""
        assert deparameterize_name("") == ""
        assert deparameterize_name("   ") == ""

    @pytest.mark.unit
    def test_handles_multiple_words(self):
        """Should handle multi-word names."""
        assert deparameterize_name("Van der Bergs") == "Van der Berg"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Smiths", "Smith"),
            ("Jones", "Jones"),
            ("The Millers", "The Miller"),
            ("Browns", "Brown"),
            ("Williams", "Williams"),
            ("Thompsons", "Thompson"),
            ("Davis", "Davis"),
        ],
    )
    def test_deparameterize_various_names(self, input_name, expected):
        """Parameterized test for various name patterns."""
        assert deparameterize_name(input_name) == expected


class TestSmartTitleCase:
    """Tests for smart title case with special name rules."""

    # Basic title case tests
    @pytest.mark.unit
    def test_basic_title_case(self):
        """Should apply basic title case to simple names."""
        assert smart_title_case("smith") == "Smith"
        assert smart_title_case("JOHNSON") == "Johnson"
        assert smart_title_case("o'REILLY") == "O'Reilly"

    # Apostrophe tests
    @pytest.mark.unit
    def test_apostrophe_names(self):
        """Should capitalize both parts of apostrophe names."""
        assert smart_title_case("o'brian") == "O'Brian"
        assert smart_title_case("O'BRIAN") == "O'Brian"
        assert smart_title_case("d'angelo") == "D'Angelo"
        assert smart_title_case("o'reilly") == "O'Reilly"

    # Hyphen tests
    @pytest.mark.unit
    def test_hyphenated_names(self):
        """Should capitalize each part of hyphenated names."""
        assert smart_title_case("smith-jones") == "Smith-Jones"
        assert smart_title_case("TAYLOR-BROWN") == "Taylor-Brown"
        assert smart_title_case("van-dyke") == "Van-Dyke"

    # Mac/Mc prefix tests
    @pytest.mark.unit
    def test_mc_names(self):
        """Should add internal capital to Mc names."""
        assert smart_title_case("mcdonald") == "McDonald"
        assert smart_title_case("mcgregor") == "McGregor"
        assert smart_title_case("mcintyre") == "McIntyre"
        assert smart_title_case("MCDONALD") == "McDonald"

    @pytest.mark.unit
    def test_mac_names(self):
        """Should add internal capital to Mac names."""
        assert smart_title_case("macdonald") == "MacDonald"
        assert smart_title_case("macleod") == "MacLeod"
        assert smart_title_case("mackenzie") == "MacKenzie"
        assert smart_title_case("MACDONALD") == "MacDonald"

    @pytest.mark.unit
    def test_mac_exceptions(self):
        """Should NOT add internal capital to Mac exceptions."""
        assert smart_title_case("macintosh") == "Macintosh"
        assert smart_title_case("machine") == "Machine"
        assert smart_title_case("MACINTOSH") == "Macintosh"
        assert smart_title_case("mach") == "Mach"
        assert smart_title_case("macro") == "Macro"
        assert smart_title_case("mace") == "Mace"

    # Particle tests
    @pytest.mark.unit
    def test_particles_lowercase_when_not_first(self):
        """Should lowercase particles when not first word."""
        assert smart_title_case("john van der berg") == "John van der Berg"
        assert smart_title_case("maria von trapp") == "Maria von Trapp"
        assert smart_title_case("jean de la fontaine") == "Jean de la Fontaine"
        assert smart_title_case("leonardo da vinci") == "Leonardo da Vinci"

    @pytest.mark.unit
    def test_particles_capitalized_when_first(self):
        """Should capitalize particles when they are the first word."""
        assert smart_title_case("van der berg") == "Van der Berg"
        assert smart_title_case("von trapp") == "Von Trapp"
        assert smart_title_case("de la cruz") == "De la Cruz"

    # Suffix tests
    @pytest.mark.unit
    def test_roman_numeral_suffixes(self):
        """Should uppercase Roman numeral suffixes."""
        assert smart_title_case("john smith ii") == "John Smith II"
        assert smart_title_case("john smith iii") == "John Smith III"
        assert smart_title_case("john smith iv") == "John Smith IV"
        assert smart_title_case("john smith v") == "John Smith V"

    @pytest.mark.unit
    def test_jr_sr_suffixes(self):
        """Should format Jr. and Sr. with period."""
        assert smart_title_case("john smith jr") == "John Smith Jr."
        assert smart_title_case("john smith sr") == "John Smith Sr."
        assert smart_title_case("JOHN SMITH JR") == "John Smith Jr."

    # Complex combination tests
    @pytest.mark.unit
    def test_complex_names(self):
        """Should handle complex names with multiple special rules."""
        assert smart_title_case("john o'brien-mcdonald iii") == "John O'Brien-McDonald III"
        assert smart_title_case("jean de macdonald") == "Jean de MacDonald"
        assert smart_title_case("patrick o'macgregor jr") == "Patrick O'MacGregor Jr."

    # Edge cases
    @pytest.mark.unit
    def test_empty_string(self):
        """Should handle empty strings gracefully."""
        assert smart_title_case("") == ""

    @pytest.mark.unit
    def test_single_word(self):
        """Should handle single word names."""
        assert smart_title_case("smith") == "Smith"
        assert smart_title_case("mcdonald") == "McDonald"

    @pytest.mark.unit
    def test_all_caps_input(self):
        """Should properly format all-caps input."""
        assert smart_title_case("JOHN MCDONALD") == "John McDonald"
        assert smart_title_case("MARY O'REILLY") == "Mary O'Reilly"

    @pytest.mark.unit
    def test_mixed_case_input(self):
        """Should properly format mixed-case input."""
        assert smart_title_case("jOhN sMiTh") == "John Smith"
        assert smart_title_case("mCdOnAlD") == "McDonald"

    # Parameterized comprehensive test
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            # Basic
            ("smith", "Smith"),
            ("JONES", "Jones"),
            # Apostrophes
            ("o'brian", "O'Brian"),
            ("d'angelo", "D'Angelo"),
            # Hyphens
            ("smith-jones", "Smith-Jones"),
            # Mc/Mac
            ("mcdonald", "McDonald"),
            ("macdonald", "MacDonald"),
            ("macintosh", "Macintosh"),  # Exception
            # Particles
            ("van der berg", "Van der Berg"),  # First word
            ("john von trapp", "John von Trapp"),  # Not first
            # Suffixes
            ("john smith ii", "John Smith II"),
            ("john smith jr", "John Smith Jr."),
            # Complex
            ("jean de macdonald", "Jean de MacDonald"),
            ("o'brien-mcdonald", "O'Brien-McDonald"),
        ],
    )
    def test_smart_title_case_comprehensive(self, input_name, expected):
        """Comprehensive parameterized test for various name patterns."""
        assert smart_title_case(input_name) == expected


class TestNameFormattingIntegration:
    """Integration tests combining multiple formatting functions."""

    @pytest.mark.unit
    def test_full_name_pipeline(self):
        """Test the full pipeline: deparameterize then smart_title_case."""
        # Start with "the mcdonalds"
        step1 = deparameterize_name("The McDonalds")
        assert step1 == "The McDonald"

        step2 = smart_title_case(step1.lower())
        assert step2 == "The McDonald"

    @pytest.mark.unit
    def test_complex_family_name_pipeline(self):
        """Test complex names through full pipeline."""
        # "the o'brien-smiths" -> "The O'Brien-Smith"
        step1 = deparameterize_name("The O'Brien-Smiths")
        assert step1 == "The O'Brien-Smith"

        # Should preserve formatting from deparameterize
        step2 = smart_title_case(step1.lower())
        assert step2 == "The O'Brien-Smith"
