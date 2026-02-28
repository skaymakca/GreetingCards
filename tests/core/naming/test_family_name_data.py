"""Tests for app.core.naming.family_name.data module — normalized lookup."""

import pytest

from app.core.naming.family_name.data import FamilyNameDatabase, FamilyNameEntry, FilteredNames, family_name_db


def _entry(display: str, rank: int = 0, count: int = 0, alternates: tuple[str, ...] = ()) -> FamilyNameEntry:
    """Shorthand factory for test entries."""
    return FamilyNameEntry(display, rank, count, alternates)


class TestFamilyNameDatabase:
    """Tests for FamilyNameDatabase container."""

    def test_contains_name(self):
        entries = {
            "morales": _entry("Morales", 52, 110842),
            "jones": _entry("Jones", 5, 1425470),
        }
        db = FamilyNameDatabase(entries)
        assert "Morales" in db
        assert "Jones" in db

    def test_case_insensitive(self):
        entries = {"morales": _entry("Morales", 52, 110842)}
        db = FamilyNameDatabase(entries)
        assert "MORALES" in db
        assert "morales" in db
        assert "MoRaLeS" in db

    def test_punctuation_insensitive(self):
        """Apostrophes, hyphens, and periods are stripped for lookup."""
        entries = {"obrien": _entry("O'Brien", 258, 118557)}
        db = FamilyNameDatabase(entries)
        assert "O'Brien" in db
        assert "O\u2019Brien" in db  # curly apostrophe
        assert "O-Brien" in db
        assert "O.Brien" in db

    def test_space_insensitive(self):
        """Spaces are stripped for lookup."""
        entries = {"delacruz": _entry("Delacruz", 458, 72109)}
        db = FamilyNameDatabase(entries)
        assert "De La Cruz" in db
        assert "de la cruz" in db
        assert "DELACRUZ" in db

    def test_not_contains(self):
        entries = {"morales": _entry("Morales", 52, 110842)}
        db = FamilyNameDatabase(entries)
        assert "Smith" not in db
        assert "" not in db

    def test_non_string_returns_false(self):
        entries = {"morales": _entry("Morales", 52, 110842)}
        db = FamilyNameDatabase(entries)
        assert 42 not in db
        assert None not in db

    def test_len(self):
        entries = {
            "a": _entry("A"),
            "b": _entry("B"),
            "c": _entry("C"),
        }
        db = FamilyNameDatabase(entries)
        assert len(db) == 3

    def test_empty(self):
        db = FamilyNameDatabase({})
        assert len(db) == 0
        assert not db
        assert "anything" not in db

    def test_bool_true_when_populated(self):
        entries = {"a": _entry("A")}
        db = FamilyNameDatabase(entries)
        assert db

    def test_normalize_static_method(self):
        assert FamilyNameDatabase.normalize("O'Brien") == "obrien"
        assert FamilyNameDatabase.normalize("De La Cruz") == "delacruz"
        assert FamilyNameDatabase.normalize("St. James") == "stjames"
        assert FamilyNameDatabase.normalize("SMITH") == "smith"
        assert FamilyNameDatabase.normalize("") == ""

    def test_normalize_unicode_special_chars(self):
        """Unicode special characters (ß, ø, æ, etc.) are manually mapped (line 81)."""
        assert FamilyNameDatabase.normalize("Straße") == "strasse"
        assert FamilyNameDatabase.normalize("Ødegård") == "odegard"
        assert FamilyNameDatabase.normalize("Æther") == "aether"
        assert FamilyNameDatabase.normalize("Þorsson") == "thorsson"
        assert FamilyNameDatabase.normalize("Đurić") == "duric"
        assert FamilyNameDatabase.normalize("Łukasz") == "lukasz"

    def test_lookup_returns_entry(self):
        entries = {"obrien": _entry("O'Brien", 258, 118557, ("O Brien",))}
        db = FamilyNameDatabase(entries)
        entry = db.lookup("O'Brien")
        assert entry is not None
        assert entry.display_form == "O'Brien"
        assert entry.rank == 258
        assert entry.count == 118557
        assert entry.alternates == ("O Brien",)

    def test_lookup_returns_none_for_missing(self):
        db = FamilyNameDatabase({})
        assert db.lookup("Smith") is None

    def test_display(self):
        entries = {"obrien": _entry("O'Brien", 258, 118557)}
        db = FamilyNameDatabase(entries)
        assert db.display("OBRIEN") == "O'Brien"
        assert db.display("o'brien") == "O'Brien"
        assert db.display("nonexistent") is None

    def test_rank_and_count(self):
        entries = {"smith": _entry("Smith", 1, 2442977)}
        db = FamilyNameDatabase(entries)
        assert db.rank("Smith") == 1
        assert db.count("Smith") == 2442977
        assert db.rank("nonexistent") == 0
        assert db.count("nonexistent") == 0


class TestFamilyNameDatabaseAlternates:
    """Tests for alternates support."""

    def test_alternates_method(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500, ("Van-Dyke", "van Dyke"))}
        db = FamilyNameDatabase(entries)
        assert db.alternates("Van Dyke") == ("Van-Dyke", "van Dyke")
        assert db.alternates("nonexistent") == ()

    def test_match_display_primary(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500, ("Van-Dyke",))}
        db = FamilyNameDatabase(entries)
        assert db.match_display("Van Dyke") == "Van Dyke"

    def test_match_display_alternate(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500, ("Van-Dyke",))}
        db = FamilyNameDatabase(entries)
        assert db.match_display("Van-Dyke") == "Van-Dyke"

    def test_match_display_none_for_unknown(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500)}
        db = FamilyNameDatabase(entries)
        assert db.match_display("Totally Unknown") is None

    def test_related_forms_from_primary(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500, ("Van-Dyke", "van Dyke"))}
        db = FamilyNameDatabase(entries)
        # Matching "Van Dyke" (primary) → returns alternates
        related = db.related_forms("Van Dyke")
        assert "Van-Dyke" in related
        assert "van Dyke" in related
        assert "Van Dyke" not in related

    def test_related_forms_from_alternate(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500, ("Van-Dyke",))}
        db = FamilyNameDatabase(entries)
        # Matching "Van-Dyke" (alternate) → returns primary
        related = db.related_forms("Van-Dyke")
        assert "Van Dyke" in related
        assert "Van-Dyke" not in related

    def test_related_forms_empty_for_unknown(self):
        entries = {"vandyke": _entry("Van Dyke", 1000, 500)}
        db = FamilyNameDatabase(entries)
        assert db.related_forms("Unknown") == []

    def test_related_forms_missing_entry_returns_empty(self):
        """When display_index hits but _entries misses, return [] (line 147)."""
        db = FamilyNameDatabase({})
        # Manually inject a display_index entry pointing to a non-existent norm_key
        db._display_index["ghost"] = ("Ghost", "nonexistent_norm_key")
        assert db.related_forms("Ghost") == []

    def test_related_forms_empty_when_no_alternates(self):
        entries = {"smith": _entry("Smith", 1, 2442977)}
        db = FamilyNameDatabase(entries)
        # Smith has no alternates, so matching primary returns empty
        assert db.related_forms("Smith") == []

    def test_entry_alternates_default_empty(self):
        entry = _entry("Smith", 1, 2442977)
        assert entry.alternates == ()


class TestFamilyNameDatabaseLoad:
    """Tests for FamilyNameDatabase.load() — loads actual data file."""

    def test_loads_nonempty(self):
        """The production data file should load with hundreds of thousands of names."""
        db = FamilyNameDatabase.load()
        assert len(db) > 100000

    def test_census_names_present(self):
        db = FamilyNameDatabase.load()
        assert "Morales" in db
        assert "Jones" in db
        assert "Williams" in db
        assert "Torres" in db
        assert "Adams" in db

    def test_display_forms(self):
        db = FamilyNameDatabase.load()
        assert db.display("OBRIEN") == "O'Brien"
        assert db.display("MCDONALD") == "McDonald"
        assert db.display("MACDONALD") == "MacDonald"
        assert db.display("SMITH") == "Smith"

    def test_census_rank_data(self):
        db = FamilyNameDatabase.load()
        assert db.rank("Smith") == 1
        assert db.count("Smith") > 0

    def test_alternates_loaded(self):
        """At least some entries should have alternates from source conflicts."""
        db = FamilyNameDatabase.load()
        # O'Brien should have an alternate (e.g. "Obrien" from Census heuristic)
        obrien_alts = db.alternates("O'Brien")
        assert len(obrien_alts) > 0


class TestFamilyNameDatabaseLoadEdgeCases:
    """Edge case tests for FamilyNameDatabase.load()."""

    def test_missing_file_returns_empty(self, tmp_path):
        """Missing database file returns empty DB with a warning (lines 159-160)."""
        from unittest.mock import patch

        with patch(
            "app.core.naming.family_name.data.get_runtime_content_path", return_value=tmp_path / "nonexistent.tsv.gz"
        ):
            db = FamilyNameDatabase.load()
        assert len(db) == 0

    def test_malformed_lines_skipped(self, tmp_path):
        """Lines with fewer than 4 TSV fields are skipped (line 169)."""
        import gzip
        from unittest.mock import patch

        gz_path = tmp_path / "test.tsv.gz"
        content = "# comment line\nmalformed\ttwo\tthree\nsmith\tSmith\t1\t2442977\n"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            f.write(content)

        with patch("app.core.naming.family_name.data.get_runtime_content_path", return_value=gz_path):
            db = FamilyNameDatabase.load()
        assert len(db) == 1
        assert "Smith" in db


class TestFamilyNameDatabaseSingleton:
    """Tests for module-level family_name_db singleton."""

    def test_singleton_loaded(self):
        assert len(family_name_db) > 100000


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
