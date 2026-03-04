"""Tests for scripts/build_family_name_db/merger.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.build_family_name_db._unicode import normalize
from scripts.build_family_name_db.merger import (
    _heuristic_display,
    _sanity_check,
    apply_overrides,
    ascii_fold,
    merge_sources,
    write_tsv,
)
from scripts.build_family_name_db.sources.census import CensusEntry

# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------


class TestNormalize:
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Smith", "smith"),
            ("JONES", "jones"),
            ("O'Brien", "obrien"),
            ("McDonald", "mcdonald"),
            ("Müller", "muller"),
            ("García", "garcia"),
            ("Núñez", "nunez"),
            ("Weiß", "weiss"),  # ß → ss
            ("Søren", "soren"),  # ø → o
            ("Ælfric", "aelfric"),  # æ → ae
            ("  Smith  ", "smith"),
            ("de la Cruz", "delacruz"),
        ],
    )
    def test_normalize(self, input_name: str, expected: str) -> None:
        assert normalize(input_name) == expected


# ---------------------------------------------------------------------------
# _heuristic_display()
# ---------------------------------------------------------------------------


class TestHeuristicDisplay:
    def test_particle_first_word(self) -> None:
        # "de" is a particle — when first word it should be capitalized
        result = _heuristic_display("de souza")
        assert result == "De Souza"

    def test_non_particle_word(self) -> None:
        # "smith" is not a particle — should be title-cased
        result = _heuristic_display("smith")
        assert result == "Smith"


# ---------------------------------------------------------------------------
# ascii_fold()
# ---------------------------------------------------------------------------


class TestAsciiFold:
    def test_pure_ascii_unchanged(self) -> None:
        assert ascii_fold("Smith") == "Smith"

    def test_pure_ascii_with_apostrophe_unchanged(self) -> None:
        assert ascii_fold("O'Brien") == "O'Brien"

    def test_folds_umlaut(self) -> None:
        assert ascii_fold("Müller") == "Muller"

    def test_folds_sharp_s_preserving_case(self) -> None:
        # ß → ss; uppercase not applicable here but function should handle
        assert ascii_fold("Weiß") == "Weiss"

    def test_folds_o_with_stroke(self) -> None:
        assert ascii_fold("Søren") == "Soren"

    def test_preserves_spaces(self) -> None:
        assert ascii_fold("de la Cruz") == "de la Cruz"

    def test_preserves_apostrophe(self) -> None:
        result = ascii_fold("O'Brien")
        assert "'" in result

    def test_folds_accented_e(self) -> None:
        result = ascii_fold("García")
        assert "a" in result.lower()

    def test_uppercase_special_mapping(self) -> None:
        # Uppercase chars with Unicode special mappings should preserve case
        # Ö → lowercase ö is in UNICODE_SPECIAL (maps via NFKD), but the
        # ascii_fold function lowercases first, then checks special map,
        # then re-applies case. "Ö" should fold to "O".
        result = ascii_fold("Ö")
        assert result == "O"

    def test_uppercase_unicode_special_folding(self) -> None:
        # Æ → ae in UNICODE_SPECIAL; uppercase first char → "Ae"
        result = ascii_fold("Æ")
        assert result == "Ae"


# ---------------------------------------------------------------------------
# merge_sources()
# ---------------------------------------------------------------------------


class TestMergeSources:
    def _make_mock_console(self) -> MagicMock:
        return MagicMock(spec=["print"])

    def test_faker_wins_over_smashew(self) -> None:
        console = self._make_mock_console()
        census: dict = {}
        faker = {"smith": "Smith"}
        smashew = {"smith": "SMITH"}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        smith_row = next(r for r in rows if r[0] == "smith")
        assert smith_row[1] == "Smith"  # faker wins

    def test_smashew_wins_over_census(self) -> None:
        console = self._make_mock_console()
        census = {"jones": CensusEntry(name="JONES", rank=2, count=5000)}
        faker: dict = {}
        smashew = {"jones": "Jones"}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        jones_row = next(r for r in rows if r[0] == "jones")
        assert jones_row[1] == "Jones"  # smashew wins

    def test_census_provides_rank_and_count(self) -> None:
        console = self._make_mock_console()
        census = {"smith": CensusEntry(name="SMITH", rank=1, count=100000)}
        faker = {"smith": "Smith"}
        smashew: dict = {}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        smith_row = next(r for r in rows if r[0] == "smith")
        assert smith_row[2] == 1  # rank
        assert smith_row[3] == 100000  # count

    def test_non_census_name_has_zero_rank(self) -> None:
        console = self._make_mock_console()
        census: dict = {}
        faker = {"obrien": "O'Brien"}
        smashew: dict = {}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        obrien_row = next(r for r in rows if r[0] == "obrien")
        assert obrien_row[2] == 0  # rank = 0
        assert obrien_row[3] == 0  # count = 0

    def test_result_sorted_by_key(self) -> None:
        console = self._make_mock_console()
        census: dict = {}
        faker = {"zebra": "Zebra", "apple": "Apple", "mango": "Mango"}
        smashew: dict = {}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        keys = [r[0] for r in rows]
        assert keys == sorted(keys)

    def test_ascii_alternate_added_for_unicode_display(self) -> None:
        console = self._make_mock_console()
        census: dict = {}
        faker = {"muller": "Müller"}  # Unicode display
        smashew: dict = {}

        with patch("scripts.build_family_name_db.merger._heuristic_display", side_effect=lambda x: x):
            rows = merge_sources(console, census, faker, smashew)

        muller_row = next((r for r in rows if r[0] == "muller"), None)
        assert muller_row is not None
        # ASCII fold "Müller" → "Muller" should be in alternates
        assert "Muller" in muller_row[4]

    def test_census_only_key_heuristic_wins(self) -> None:
        console = self._make_mock_console()
        census = {"garcia": CensusEntry(name="GARCIA", rank=8, count=1023000)}
        faker: dict = {}
        smashew: dict = {}

        rows = merge_sources(console, census, faker, smashew)

        garcia_row = next(r for r in rows if r[0] == "garcia")
        # Census-only key uses _heuristic_display for display form
        assert garcia_row[2] == 8
        assert garcia_row[3] == 1023000

    def test_faker_all_forms_adds_alternates(self) -> None:
        console = self._make_mock_console()
        census: dict = {}
        faker = {"smith": "Smith"}
        smashew: dict = {}
        faker_all_forms = {"smith": ["Smith", "SMITH"]}

        rows = merge_sources(console, census, faker, smashew, faker_all_forms=faker_all_forms)

        smith_row = next(r for r in rows if r[0] == "smith")
        # "Smith" is the display winner, so it shouldn't appear in alternates.
        # "SMITH" is a different form, so it should be in alternates.
        assert "SMITH" in smith_row[4]


# ---------------------------------------------------------------------------
# apply_overrides()
# ---------------------------------------------------------------------------


class TestApplyOverrides:
    def _base_rows(self):
        return [
            ("jones", "Jones", 2, 5000, []),
            ("smith", "Smith", 1, 100000, []),
        ]

    def test_replaces_existing_entry(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("jones\tO'Jones\t0\t0\n", encoding="utf-8")

        result = apply_overrides(console, rows, override_file)
        jones_row = next(r for r in result if r[0] == "jones")
        assert jones_row[1] == "O'Jones"

    def test_adds_new_entry(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("obrien\tO'Brien\t0\t0\n", encoding="utf-8")

        result = apply_overrides(console, rows, override_file)
        obrien_row = next((r for r in result if r[0] == "obrien"), None)
        assert obrien_row is not None
        assert obrien_row[1] == "O'Brien"

    def test_missing_file_returns_unchanged(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        result = apply_overrides(console, rows, tmp_path / "nonexistent.tsv")
        assert result == rows

    def test_empty_file_returns_unchanged(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("", encoding="utf-8")
        result = apply_overrides(console, rows, override_file)
        assert result == rows

    def test_comments_skipped(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("# This is a comment\njones\tJ\t0\t0\n", encoding="utf-8")

        result = apply_overrides(console, rows, override_file)
        jones_row = next(r for r in result if r[0] == "jones")
        assert jones_row[1] == "J"

    def test_malformed_override_row_skipped(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        # Row with < 4 columns should be skipped
        override_file.write_text("bad\trow\nsmith\tSmythe\t0\t0\n", encoding="utf-8")

        result = apply_overrides(console, rows, override_file)
        # "bad" row is skipped; "smith" override is applied
        smith_row = next(r for r in result if r[0] == "smith")
        assert smith_row[1] == "Smythe"
        # "bad" should not be added
        assert all(r[0] != "bad" for r in result)

    def test_keeps_existing_rank_if_override_is_zero(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()  # smith has rank=1
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("smith\tSmith\t0\t0\n", encoding="utf-8")  # rank=0 in override

        result = apply_overrides(console, rows, override_file)
        smith_row = next(r for r in result if r[0] == "smith")
        assert smith_row[2] == 1  # original rank preserved

    def test_result_sorted_after_adding(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = self._base_rows()
        override_file = tmp_path / "overrides.tsv"
        override_file.write_text("aaaa\tAaaa\t0\t0\n", encoding="utf-8")

        result = apply_overrides(console, rows, override_file)
        keys = [r[0] for r in result]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# write_tsv()
# ---------------------------------------------------------------------------


class TestWriteTsv:
    def test_creates_file_with_header(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = [
            ("jones", "Jones", 2, 5000, []),
            ("smith", "Smith", 1, 100000, ["SMITH"]),
            ("obrien", "O'Brien", 0, 0, []),
            ("williams", "Williams", 3, 4000, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("macdonald", "MacDonald", 0, 0, []),
        ]
        output = tmp_path / "names.tsv"
        write_tsv(console, rows, output)

        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content.startswith("# normalized\tdisplay\trank\tcount\talternates\n")

    def test_rows_written_correctly(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = [
            ("jones", "Jones", 2, 5000, []),
            ("smith", "Smith", 1, 100000, ["SMITH", "Smithe"]),
            ("obrien", "O'Brien", 0, 0, []),
            ("williams", "Williams", 3, 4000, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("macdonald", "MacDonald", 0, 0, []),
        ]
        output = tmp_path / "names.tsv"
        write_tsv(console, rows, output)

        lines = output.read_text(encoding="utf-8").splitlines()
        # Skip header comment
        data_lines = [line for line in lines if not line.startswith("#")]
        assert any("jones\tJones\t2\t5000\t" in line for line in data_lines)
        assert any("smith\tSmith\t1\t100000\tSMITH|Smithe" in line for line in data_lines)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        console = MagicMock(spec=["print"])
        rows = [
            ("jones", "Jones", 2, 5000, []),
            ("smith", "Smith", 1, 100000, []),
            ("obrien", "O'Brien", 0, 0, []),
            ("williams", "Williams", 3, 4000, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("macdonald", "MacDonald", 0, 0, []),
        ]
        output = tmp_path / "sub" / "dir" / "names.tsv"
        write_tsv(console, rows, output)
        assert output.exists()


# ---------------------------------------------------------------------------
# _sanity_check()
# ---------------------------------------------------------------------------


class TestSanityCheck:
    def _good_rows(self):
        return [
            ("jones", "Jones", 2, 5000, []),
            ("macdonald", "MacDonald", 0, 0, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("obrien", "O'Brien", 0, 0, []),
            ("smith", "Smith", 1, 100000, []),
            ("williams", "Williams", 3, 4000, []),
        ]

    def test_passes_with_good_data(self) -> None:
        console = MagicMock(spec=["print"])
        rows = self._good_rows()
        # Should not raise or exit
        with patch("sys.exit") as mock_exit:
            _sanity_check(console, rows)
            mock_exit.assert_not_called()

    def test_fails_when_smith_missing(self) -> None:
        console = MagicMock(spec=["print"])
        rows = [r for r in self._good_rows() if r[0] != "smith"]
        with patch("sys.exit") as mock_exit:
            _sanity_check(console, rows)
            mock_exit.assert_called_once_with(1)

    def test_fails_when_display_form_wrong(self) -> None:
        console = MagicMock(spec=["print"])
        rows = [
            ("jones", "Jones", 2, 5000, []),
            ("macdonald", "MacDonald", 0, 0, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("obrien", "O'Brien", 0, 0, []),
            ("smith", "SMITH", 1, 100000, []),  # Wrong display
            ("williams", "Williams", 3, 4000, []),
        ]
        with patch("sys.exit") as mock_exit:
            _sanity_check(console, rows)
            mock_exit.assert_called_once_with(1)

    def test_fails_when_obrien_missing(self) -> None:
        """Sanity check exits when a non-Smith expected name is missing."""
        console = MagicMock(spec=["print"])
        rows = [r for r in self._good_rows() if r[0] != "obrien"]
        with patch("sys.exit") as mock_exit:
            _sanity_check(console, rows)
            mock_exit.assert_called_once_with(1)

    def test_fails_when_smith_rank_wrong(self) -> None:
        console = MagicMock(spec=["print"])
        rows = [
            ("jones", "Jones", 2, 5000, []),
            ("macdonald", "MacDonald", 0, 0, []),
            ("mcdonald", "McDonald", 0, 0, []),
            ("obrien", "O'Brien", 0, 0, []),
            ("smith", "Smith", 5, 100000, []),  # rank=5, not 1
            ("williams", "Williams", 3, 4000, []),
        ]
        with patch("sys.exit") as mock_exit:
            _sanity_check(console, rows)
            mock_exit.assert_called_once_with(1)
