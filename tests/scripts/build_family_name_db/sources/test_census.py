"""Tests for scripts/build_family_name_db/sources/census.py."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.build_family_name_db.sources.census import (
    CensusEntry,
    download_census,
    normalize,
)


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
            ("Weiß", "weiss"),
            ("Søren", "soren"),
        ],
    )
    def test_normalize(self, input_name: str, expected: str) -> None:
        assert normalize(input_name) == expected


def _make_census_zip(rows: list[dict]) -> bytes:
    """Build an in-memory zip containing a Census-format CSV."""
    csv_content = io.StringIO()
    fieldnames = [
        "name",
        "rank",
        "count",
        "prop100k",
        "cum_prop100k",
        "pctwhite",
        "pctblack",
        "pctapi",
        "pctaian",
        "pct2prace",
        "pcthispanic",
    ]
    writer = csv.DictWriter(csv_content, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("Names_2010Census.csv", csv_content.getvalue())
    return zip_buffer.getvalue()


class TestDownloadCensus:
    def _make_mock_console(self) -> MagicMock:
        return MagicMock(spec=["print"])

    def test_downloads_and_parses_csv(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        zip_data = _make_census_zip(
            [
                {
                    "name": "SMITH",
                    "rank": "1",
                    "count": "100000",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
                {
                    "name": "JONES",
                    "rank": "2",
                    "count": "50000",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
            ]
        )

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=zip_data)

        with patch("scripts.build_family_name_db.sources.census.urlopen", return_value=mock_resp):
            result = download_census(console, tmp_path)

        assert "smith" in result
        assert "jones" in result
        assert result["smith"].rank == 1
        assert result["smith"].count == 100000
        assert result["jones"].rank == 2

    def test_uses_cached_zip_when_exists(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        zip_data = _make_census_zip(
            [
                {
                    "name": "SMITH",
                    "rank": "1",
                    "count": "100000",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
            ]
        )
        # Write the zip to cache
        cache_zip = tmp_path / "names.zip"
        cache_zip.write_bytes(zip_data)

        with patch("scripts.build_family_name_db.sources.census.urlopen") as mock_urlopen:
            result = download_census(console, tmp_path)
            mock_urlopen.assert_not_called()

        assert "smith" in result

    def test_suppressed_values_become_zero(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        zip_data = _make_census_zip(
            [
                {
                    "name": "RARE",
                    "rank": "(S)",
                    "count": "(S)",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
            ]
        )

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=zip_data)

        with patch("scripts.build_family_name_db.sources.census.urlopen", return_value=mock_resp):
            result = download_census(console, tmp_path)

        assert "rare" in result
        assert result["rare"].rank == 0
        assert result["rare"].count == 0

    def test_empty_names_skipped(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        zip_data = _make_census_zip(
            [
                {
                    "name": "",
                    "rank": "1",
                    "count": "100",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
                {
                    "name": "SMITH",
                    "rank": "2",
                    "count": "50",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
            ]
        )

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=zip_data)

        with patch("scripts.build_family_name_db.sources.census.urlopen", return_value=mock_resp):
            result = download_census(console, tmp_path)

        assert "" not in result
        assert "smith" in result

    def test_census_entry_preserves_original_name(self, tmp_path: Path) -> None:
        console = self._make_mock_console()
        zip_data = _make_census_zip(
            [
                {
                    "name": "O'BRIEN",
                    "rank": "5",
                    "count": "2000",
                    "prop100k": "",
                    "cum_prop100k": "",
                    "pctwhite": "",
                    "pctblack": "",
                    "pctapi": "",
                    "pctaian": "",
                    "pct2prace": "",
                    "pcthispanic": "",
                },
            ]
        )

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read = MagicMock(return_value=zip_data)

        with patch("scripts.build_family_name_db.sources.census.urlopen", return_value=mock_resp):
            result = download_census(console, tmp_path)

        entry = result["obrien"]
        assert entry.name == "O'BRIEN"
        assert isinstance(entry, CensusEntry)
