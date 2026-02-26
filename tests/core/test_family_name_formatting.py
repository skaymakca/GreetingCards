"""Tests for app.core.family_name.formatting module."""

import pytest

from app.core.family_name.formatting import smart_title_case_family_name


class TestSmartTitleCaseFamilyName:
    """Tests for smart title case with special name rules."""

    # Basic title case
    def test_basic_title_case(self):
        assert smart_title_case_family_name("smith") == "Smith"
        assert smart_title_case_family_name("JOHNSON") == "Johnson"
        assert smart_title_case_family_name("o'REILLY") == "O'Reilly"

    # Apostrophe names
    def test_apostrophe_names(self):
        assert smart_title_case_family_name("o'brian") == "O'Brian"
        assert smart_title_case_family_name("O'BRIAN") == "O'Brian"
        assert smart_title_case_family_name("d'angelo") == "D'Angelo"
        assert smart_title_case_family_name("o'reilly") == "O'Reilly"

    # Hyphenated names
    def test_hyphenated_names(self):
        assert smart_title_case_family_name("smith-jones") == "Smith-Jones"
        assert smart_title_case_family_name("TAYLOR-BROWN") == "Taylor-Brown"
        assert smart_title_case_family_name("van-dyke") == "Van-Dyke"

    # Mc/Mac prefixes
    def test_mc_names(self):
        assert smart_title_case_family_name("mcdonald") == "McDonald"
        assert smart_title_case_family_name("mcgregor") == "McGregor"
        assert smart_title_case_family_name("mcintyre") == "McIntyre"
        assert smart_title_case_family_name("MCDONALD") == "McDonald"

    def test_mac_names(self):
        assert smart_title_case_family_name("macdonald") == "MacDonald"
        assert smart_title_case_family_name("macleod") == "MacLeod"
        assert smart_title_case_family_name("mackenzie") == "MacKenzie"
        assert smart_title_case_family_name("MACDONALD") == "MacDonald"

    def test_mac_exceptions(self):
        assert smart_title_case_family_name("macintosh") == "Macintosh"
        assert smart_title_case_family_name("machine") == "Machine"
        assert smart_title_case_family_name("MACINTOSH") == "Macintosh"
        assert smart_title_case_family_name("mach") == "Mach"
        assert smart_title_case_family_name("macro") == "Macro"
        assert smart_title_case_family_name("mace") == "Mace"

    # Particles
    def test_particles_lowercase_when_not_first(self):
        assert smart_title_case_family_name("john van der berg") == "John van der Berg"
        assert smart_title_case_family_name("maria von trapp") == "Maria von Trapp"
        assert smart_title_case_family_name("jean de la fontaine") == "Jean de la Fontaine"
        assert smart_title_case_family_name("leonardo da vinci") == "Leonardo da Vinci"

    def test_particles_capitalized_when_first(self):
        assert smart_title_case_family_name("van der berg") == "Van der Berg"
        assert smart_title_case_family_name("von trapp") == "Von Trapp"
        assert smart_title_case_family_name("de la cruz") == "De la Cruz"

    # Suffixes
    def test_roman_numeral_suffixes(self):
        assert smart_title_case_family_name("john smith ii") == "John Smith II"
        assert smart_title_case_family_name("john smith iii") == "John Smith III"
        assert smart_title_case_family_name("john smith iv") == "John Smith IV"
        assert smart_title_case_family_name("john smith v") == "John Smith V"

    def test_jr_sr_suffixes(self):
        assert smart_title_case_family_name("john smith jr") == "John Smith Jr."
        assert smart_title_case_family_name("john smith sr") == "John Smith Sr."
        assert smart_title_case_family_name("JOHN SMITH JR") == "John Smith Jr."

    # Complex combinations
    def test_complex_names(self):
        assert smart_title_case_family_name("john o'brien-mcdonald iii") == "John O'Brien-McDonald III"
        assert smart_title_case_family_name("jean de macdonald") == "Jean de MacDonald"
        assert smart_title_case_family_name("patrick o'macgregor jr") == "Patrick O'MacGregor Jr."

    # Edge cases
    def test_empty_string(self):
        assert smart_title_case_family_name("") == ""

    def test_single_word(self):
        assert smart_title_case_family_name("smith") == "Smith"
        assert smart_title_case_family_name("mcdonald") == "McDonald"

    def test_all_caps(self):
        assert smart_title_case_family_name("JOHN MCDONALD") == "John McDonald"
        assert smart_title_case_family_name("MARY O'REILLY") == "Mary O'Reilly"

    def test_mixed_case(self):
        assert smart_title_case_family_name("jOhN sMiTh") == "John Smith"
        assert smart_title_case_family_name("mCdOnAlD") == "McDonald"

    # Comprehensive parametrized
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("smith", "Smith"),
            ("JONES", "Jones"),
            ("o'brian", "O'Brian"),
            ("d'angelo", "D'Angelo"),
            ("smith-jones", "Smith-Jones"),
            ("mcdonald", "McDonald"),
            ("macdonald", "MacDonald"),
            ("macintosh", "Macintosh"),
            ("van der berg", "Van der Berg"),
            ("john von trapp", "John von Trapp"),
            ("john smith ii", "John Smith II"),
            ("john smith jr", "John Smith Jr."),
            ("jean de macdonald", "Jean de MacDonald"),
            ("o'brien-mcdonald", "O'Brien-McDonald"),
        ],
    )
    def test_comprehensive(self, input_name, expected):
        assert smart_title_case_family_name(input_name) == expected
