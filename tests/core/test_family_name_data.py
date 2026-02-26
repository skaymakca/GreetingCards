"""Tests for app.core.family_name.data module — normalized lookup."""

import pytest

from app.core.family_name.data import FilteredNames, PreservedFamilyNames


class TestPreservedFamilyNames:
    """Tests for PreservedFamilyNames container."""

    def test_contains_census_name(self):
        names = PreservedFamilyNames(["Morales", "Jones", "Williams"])
        assert "Morales" in names
        assert "Jones" in names

    def test_case_insensitive(self):
        names = PreservedFamilyNames(["Morales"])
        assert "MORALES" in names
        assert "morales" in names
        assert "MoRaLeS" in names

    def test_punctuation_insensitive(self):
        """Apostrophes, hyphens, and periods are stripped for lookup."""
        names = PreservedFamilyNames(["OBriens"])
        assert "O'Briens" in names
        assert "O\u2019Briens" in names  # curly apostrophe
        assert "O-Briens" in names
        assert "O.Briens" in names

    def test_space_insensitive(self):
        """Spaces are stripped for lookup."""
        names = PreservedFamilyNames(["Delacruz"])
        assert "De La Cruz" in names
        assert "de la cruz" in names
        assert "DELACRUZ" in names

    def test_not_contains(self):
        names = PreservedFamilyNames(["Morales"])
        assert "Smith" not in names
        assert "" not in names

    def test_non_string_returns_false(self):
        names = PreservedFamilyNames(["Morales"])
        assert 42 not in names
        assert None not in names

    def test_len(self):
        names = PreservedFamilyNames(["A", "B", "C"])
        assert len(names) == 3

    def test_empty(self):
        names = PreservedFamilyNames([])
        assert len(names) == 0
        assert not names
        assert "anything" not in names

    def test_bool_true_when_populated(self):
        names = PreservedFamilyNames(["A"])
        assert names

    def test_whitespace_only_entries_skipped(self):
        names = PreservedFamilyNames(["Smith", "", "  ", "\n"])
        assert len(names) == 1

    def test_normalize_static_method(self):
        assert PreservedFamilyNames.normalize("O'Brien") == "obrien"
        assert PreservedFamilyNames.normalize("De La Cruz") == "delacruz"
        assert PreservedFamilyNames.normalize("St. James") == "stjames"
        assert PreservedFamilyNames.normalize("SMITH") == "smith"
        assert PreservedFamilyNames.normalize("") == ""


class TestPreservedFamilyNamesLoad:
    """Tests for PreservedFamilyNames.load() — loads actual data file."""

    def test_loads_nonempty(self):
        """The production data file should load with thousands of names."""
        names = PreservedFamilyNames.load()
        assert len(names) > 10000

    def test_census_names_present(self):
        names = PreservedFamilyNames.load()
        assert "Morales" in names
        assert "Jones" in names
        assert "Williams" in names
        assert "Torres" in names
        assert "Adams" in names


class TestFilteredNames:
    """Tests for FilteredNames container."""

    def test_contains_known_entries(self):
        fn = FilteredNames()
        assert "family" in fn
        assert "unknown" in fn
        assert "snapfish" in fn
        assert "christmas" in fn

    def test_case_insensitive(self):
        fn = FilteredNames()
        assert "Family" in fn
        assert "FAMILY" in fn
        assert "FaMiLy" in fn

    def test_multi_word_entries(self):
        fn = FilteredNames()
        assert "New Year" in fn
        assert "Chinese New Year" in fn
        assert "Season's Greetings" in fn
        assert "Valentine's Day" in fn

    def test_real_names_not_filtered(self):
        fn = FilteredNames()
        assert "Smith" not in fn
        assert "Johnson" not in fn
        assert "Morales" not in fn

    def test_non_string_returns_false(self):
        fn = FilteredNames()
        assert 42 not in fn

    def test_len(self):
        fn = FilteredNames()
        assert len(fn) > 0
